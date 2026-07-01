"""
WW3 Wave Data Extractor for Sentinel-1 MER products.
Optimized: Load WW3 variables into memory once, then access as numpy arrays.
"""

import os
import logging
import time
import pandas as pd
import polars as pl
import numpy as np
import xarray as xr
from scipy.spatial import KDTree
from joblib import Parallel, delayed
from tqdm import tqdm
from shapely import wkt
import warnings
from functools import wraps
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)


def timing_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start_time
        if elapsed > 0.01:
            logger.debug(f"⏱️ {func.__name__} took {elapsed:.3f}s")
        return result
    return wrapper


try:
    from s1iw_catalogue.config import load_config
except ImportError:
    def load_config(config_path=None):
        import yaml
        if config_path is None:
            possible_paths = [
                os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yml'),
                os.path.join(os.path.dirname(__file__), 'config.yml'),
                os.path.join(os.getcwd(), 'config.yml'),
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    config_path = path
                    break
        if not config_path or not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found")
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)


class WW3Extractor:
    """Extract WW3 wave data with numpy array access."""
    
    def __init__(self, config_path: str = None):
        self.config = load_config(config_path)
        ww3_config = self.config.get('ww3', {})
        
        self.primary_root = ww3_config.get('primary_root', '/scale/project/wave/WW3/PROJECT/CCI/RUNS/GLOB-30M')
        self.fallback_root = ww3_config.get('fallback_root', '/scale/project/wave/WW3/FORECAST/GLOBMULTI/GLOB-30M/FIELD_NC/best_estimate')
        self.field_nc_subdir = ww3_config.get('field_nc_subdir', 'FIELD_NC')
        
        self.hs_var = ww3_config.get('hs_variable', 'hs')
        self.t01_var = ww3_config.get('t01_variable', 't01')
        self.primary_pattern = ww3_config.get('primary_pattern', 'CCI_WW3-GLOB-30M_{yearmonth}.nc')
        self.fallback_pattern = ww3_config.get('fallback_pattern', 'MARC_WW3-GLOB-30M_{datestr}Z.nc')
        
        # self.output_columns = ['mean_hs_value', 'max_hs_value', 'mean_t01_value', 'max_t01_value']
        self.output_columns = ['Hs WW3', 'Tp WW3']
        self.default_n_jobs = ww3_config.get('default_n_jobs', 6)
        
        # Cache: store loaded numpy arrays directly
        self._cache = {}
        self._cache_hits = 0
        self._cache_misses = 0
        
        self._diagnostics = {
            'total_products': 0, 'valid_geometries': 0, 'invalid_geometries': 0,
            'successful_extractions': 0, 'failed_extractions': 0,
            'sample_coords': [], 'ww3_grid_bounds': None,
            'file_not_found': 0, 'extraction_errors': []
        }
    
    @timing_decorator
    def get_nearest_ww3_hour(self, hour: int) -> int:
        ww3_hours = [0, 3, 6, 9, 12, 15, 18, 21]
        if hour == 23:
            return 0
        return min(ww3_hours, key=lambda x: abs(x - hour))
    
    @timing_decorator
    def get_ww3_filename(self, datetime_obj) -> tuple:
        rounded_hour = datetime_obj.round('h')
        if rounded_hour.hour == 23:
            rounded_hour += pd.Timedelta(hours=1)
        near_hour = self.get_nearest_ww3_hour(rounded_hour.hour)
        ww3_time = rounded_hour.replace(hour=near_hour)
        
        year = ww3_time.year
        yearmonth = ww3_time.strftime('%Y%m')
        datestr = ww3_time.strftime('%Y%m%dT%H')
        
        primary = self.primary_pattern.format(yearmonth=yearmonth)
        fallback = self.fallback_pattern.format(datestr=datestr)
        return primary, fallback, year
    
    @timing_decorator
    def get_file_path(self, year: int, primary_file: str, fallback_file: str) -> str:
        primary_path = os.path.join(self.primary_root, str(year), self.field_nc_subdir, primary_file)
        if os.path.exists(primary_path):
            return primary_path
        fallback_path = os.path.join(self.fallback_root, str(year), fallback_file)
        if os.path.exists(fallback_path):
            return fallback_path
        return None
    
    @timing_decorator
    def _parse_geometry(self, geom):
        if geom is None:
            return None
        if hasattr(geom, 'geom_type'):
            return geom
        if isinstance(geom, str):
            try:
                geom_obj = wkt.loads(geom.strip())
                if geom_obj.geom_type == 'MultiPolygon':
                    areas = [p.area for p in geom_obj.geoms]
                    geom_obj = geom_obj.geoms[np.argmax(areas)]
                if geom_obj.geom_type == 'Polygon':
                    return geom_obj
            except:
                pass
        return None
    
    def _get_centroid_from_geometry(self, row, geom_col: str):
        geom = row[geom_col]
        if geom is None:
            return np.nan, np.nan
        try:
            parsed = self._parse_geometry(geom)
            if parsed is not None and hasattr(parsed, 'centroid'):
                return parsed.centroid.x, parsed.centroid.y
        except:
            pass
        return np.nan, np.nan
    
    @timing_decorator
    def _load_ww3_data_with_times(self, filepath: str):
        """
        Load WW3 data for ALL times into memory as numpy arrays.
        We'll store the full 3D array and select the right time for each product.
        """
        if filepath in self._cache:
            self._cache_hits += 1
            return self._cache[filepath]
        
        self._cache_misses += 1
        
        logger.debug(f"  Loading {os.path.basename(filepath)} ALL times into memory...")
        
        # Open dataset
        t0 = time.time()
        ds = xr.open_dataset(filepath, engine='h5netcdf')
        t_open = time.time() - t0
        
        # Get coordinates and times
        t0 = time.time()
        lons = ds.longitude.values
        lats = ds.latitude.values
        times = ds.time.values
        lon_grid, lat_grid = np.meshgrid(lons, lats)
        
        # Build KDTree (same for all times)
        points = np.column_stack([lon_grid.ravel(), lat_grid.ravel()])
        tree = KDTree(points)
        t_grid = time.time() - t0
        
        # Load ALL time steps into memory (3D arrays: time, lat, lon)
        t0 = time.time()
        hs_data = ds[self.hs_var].load().values  # Shape: (time, lat, lon)
        t01_data = ds[self.t01_var].load().values  # Shape: (time, lat, lon)
        t_load = time.time() - t0
        
        # Close the dataset
        ds.close()
        
        logger.debug(f"  Loaded {os.path.basename(filepath)} ALL times: open={t_open:.3f}s, grid={t_grid:.3f}s, load={t_load:.3f}s")
        logger.debug(f"  Data shapes: hs={hs_data.shape}, t01={t01_data.shape} (time, lat, lon)")
        
        # Store in cache
        cache_entry = {
            'hs_data': hs_data,
            't01_data': t01_data,
            'times': times,
            'lon_grid': lon_grid,
            'lat_grid': lat_grid,
            'points': points,
            'tree': tree,
            'lons': lons,
            'lats': lats
        }
        self._cache[filepath] = cache_entry
        
        # Store grid bounds for diagnostics
        if self._diagnostics['ww3_grid_bounds'] is None:
            self._diagnostics['ww3_grid_bounds'] = {
                'lon_min': lons.min(), 'lon_max': lons.max(),
                'lat_min': lats.min(), 'lat_max': lats.max()
            }
        
        return cache_entry
    
    @timing_decorator
    def _extract_values_batch(self, cache_entry, indices, df_with_info, geom_col, time_col='start date SAFE'):
        """
        Extract values using numpy array access with correct time for each product.
        """
        results = {}
        
        hs_data = cache_entry['hs_data']  # Shape: (time, lat, lon)
        t01_data = cache_entry['t01_data']
        times = cache_entry['times']
        tree = cache_entry['tree']
        lon_grid = cache_entry['lon_grid']
        
        # Collect all centroids and times
        centroids = []
        time_indices = []
        valid_indices = []
        
        for idx in indices:
            row = df_with_info.loc[idx]
            lon, lat = self._get_centroid_from_geometry(row, geom_col)
            
            self._diagnostics['total_products'] += 1
            
            if np.isnan(lon) or np.isnan(lat):
                self._diagnostics['invalid_geometries'] += 1
                results[idx] = {col: np.nan for col in self.output_columns}
                continue
            
            # Get the time for this product
            try:
                product_time = pd.to_datetime(row[time_col])
                # Find the closest time in the WW3 dataset
                time_idx = np.argmin(np.abs(times - np.datetime64(product_time)))
            except:
                time_idx = 0  # Default to first time
            
            self._diagnostics['valid_geometries'] += 1
            centroids.append((lon, lat))
            time_indices.append(time_idx)
            valid_indices.append(idx)
            
            if len(self._diagnostics['sample_coords']) < 5:
                safe_name = row.get('SAFE SLC', 'unknown')[:40]
                self._diagnostics['sample_coords'].append((lon, lat, product_time, safe_name))
        
        if not valid_indices:
            return results
        
        # Batch KDTree query
        centroids_array = np.array(centroids)
        distances, indices_kd = tree.query(centroids_array, k=1)
        
        # Convert to lat/lon indices
        ilats, ilons = np.unravel_index(indices_kd, lon_grid.shape)
        
        # Extract values using numpy array indexing with correct time
        for i, idx in enumerate(valid_indices):
            ilat = ilats[i]
            ilon = ilons[i]
            time_idx = time_indices[i]
            
            # Check bounds
            if time_idx >= hs_data.shape[0] or ilat >= hs_data.shape[1] or ilon >= hs_data.shape[2]:
                logger.debug(f"  Index out of bounds: time={time_idx}, ilat={ilat}, ilon={ilon}, shape={hs_data.shape}")
                results[idx] = {col: np.nan for col in self.output_columns}
                continue
            
            # Direct numpy array access with time dimension!
            hs_val = float(hs_data[time_idx, ilat, ilon])
            t01_val = float(t01_data[time_idx, ilat, ilon])
            
            self._diagnostics['successful_extractions'] += 1
            
            # results[idx] = {
            #     'mean_hs_value': hs_val,
            #     'max_hs_value': hs_val,
            #     'mean_t01_value': t01_val,
            #     'max_t01_value': t01_val
            # }
            # In _extract_values_batch, when creating results:
            results[idx] = {
                'Hs WW3': hs_val,
                'Tp WW3': t01_val
            }
        
        return results
    
    def print_diagnostics(self):
        d = self._diagnostics
        logger.info("=" * 60)
        logger.info("📊 EXTRACTION DIAGNOSTICS")
        logger.info(f"   Total products: {d['total_products']}")
        logger.info(f"   Valid geometries: {d['valid_geometries']}")
        logger.info(f"   Invalid geometries: {d['invalid_geometries']}")
        logger.info(f"   Successful extractions: {d['successful_extractions']}")
        logger.info(f"   Failed extractions: {d['failed_extractions']}")
        if d['ww3_grid_bounds']:
            b = d['ww3_grid_bounds']
            logger.info(f"   WW3 grid bounds: Lon [{b['lon_min']:.1f}, {b['lon_max']:.1f}] Lat [{b['lat_min']:.1f}, {b['lat_max']:.1f}]")
        if d['sample_coords']:
            logger.info("   Sample coordinates (lon, lat, time, SAFE):")
            for coord in d['sample_coords'][:3]:
                if len(coord) == 4:
                    lon, lat, time_val, safe = coord
                    logger.info(f"      ({lon:.4f}, {lat:.4f}) {time_val} - {safe[:30]}...")
                else:
                    lon, lat, safe = coord
                    logger.info(f"      ({lon:.4f}, {lat:.4f}) - {safe[:30]}...")
        logger.info("=" * 60)
    
    @timing_decorator
    def extract_batch(self, catalogue_df, n_jobs: int = None, verbose: bool = True) -> pd.DataFrame:
        total_start = time.time()
        
        self._diagnostics = {
            'total_products': 0, 'valid_geometries': 0, 'invalid_geometries': 0,
            'successful_extractions': 0, 'failed_extractions': 0,
            'sample_coords': [], 'ww3_grid_bounds': None,
            'file_not_found': 0, 'extraction_errors': []
        }
        
        is_polars = isinstance(catalogue_df, pl.DataFrame)
        if is_polars:
            catalogue_df = catalogue_df.to_pandas()
        
        if n_jobs is None:
            n_jobs = self.default_n_jobs
        
        # Check columns
        time_col = None
        for col in ['start date SAFE', 'start_date']:
            if col in catalogue_df.columns:
                time_col = col
                break
        if time_col is None:
            raise ValueError("Missing time column")
        
        geom_col = None
        for col in ['geometry', 'polygon SLC', 'polygon GRD', 'polygon']:
            if col in catalogue_df.columns:
                geom_col = col
                break
        if geom_col is None:
            raise ValueError("No geometry column found")
        
        # Add WW3 info
        def add_ww3_info(row):
            try:
                start_date = pd.to_datetime(row[time_col])
                primary, fallback, year = self.get_ww3_filename(start_date)
                row['_ww3_primary'] = primary
                row['_ww3_fallback'] = fallback
                row['_ww3_year'] = year
            except:
                row['_ww3_primary'] = None
            return row
        
        df_with_info = catalogue_df.apply(add_ww3_info, axis=1)
        
        # Group by filename
        groups = {}
        for idx, row in df_with_info.iterrows():
            key = row['_ww3_primary']
            if key is None:
                continue
            if key not in groups:
                groups[key] = {'year': row['_ww3_year'], 'primary_file': key, 
                              'fallback_file': row['_ww3_fallback'], 'indices': []}
            groups[key]['indices'].append(idx)
        
        if verbose:
            logger.info(f"📊 Processing {len(groups)} files for {len(catalogue_df)} products")
        
        def process_group(group_info):
            indices = group_info['indices']
            year = group_info['year']
            primary_file = group_info['primary_file']
            fallback_file = group_info['fallback_file']
            
            filepath = self.get_file_path(year, primary_file, fallback_file)
            if filepath is None:
                self._diagnostics['file_not_found'] += 1
                return {idx: {col: np.nan for col in self.output_columns} for idx in indices}
            
            # Load ALL times into memory once
            cache_entry = self._load_ww3_data_with_times(filepath)
            if cache_entry is None:
                return {idx: {col: np.nan for col in self.output_columns} for idx in indices}
            
            # Extract values using numpy arrays with correct time per product
            return self._extract_values_batch(cache_entry, indices, df_with_info, geom_col, time_col)
        
        # Process groups
        group_list = list(groups.items())
        if n_jobs > 1 and len(group_list) > 0:
            all_results = Parallel(n_jobs=n_jobs, verbose=0)(
                delayed(process_group)(group_info)
                for _, group_info in tqdm(group_list, desc="Processing", disable=not verbose)
            )
        else:
            all_results = []
            for _, group_info in tqdm(group_list, desc="Processing", disable=not verbose):
                all_results.append(process_group(group_info))
        
        # Combine results
        combined_results = {}
        for result_dict in all_results:
            combined_results.update(result_dict)
        
        # Create DataFrame
        result_df = pd.DataFrame.from_dict(combined_results, orient='index')
        result_df.index.name = 'original_index'
        
        # Print diagnostics
        self.print_diagnostics()
        
        if verbose:
            logger.info(f"🏁 Total time: {time.time() - total_start:.3f}s")
            logger.info(f"   Cache: hits={self._cache_hits}, misses={self._cache_misses}")
        
        if is_polars:
            return pl.from_pandas(result_df.reset_index(drop=True))
        return result_df


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def add_ww3_to_catalogue(catalogue_df, config_path: str = None, n_jobs: int = 6, verbose: bool = True):
    extractor = WW3Extractor(config_path)
    ww3_results = extractor.extract_batch(catalogue_df, n_jobs=n_jobs, verbose=verbose)
    
    is_polars = isinstance(catalogue_df, pl.DataFrame)
    
    if is_polars:
        result_df = catalogue_df.clone()
        for col in extractor.output_columns:
            if col in ww3_results.columns:
                values = ww3_results[col].to_pandas().values
                result_df = result_df.with_columns(pl.Series(col, values))
            else:
                result_df = result_df.with_columns(pl.Series(col, [np.nan] * len(result_df)))
        return result_df
    else:
        result_df = catalogue_df.copy()
        for col in extractor.output_columns:
            if col in ww3_results.columns:
                result_df[col] = ww3_results[col].values
            else:
                result_df[col] = np.nan
        return result_df


add_ww3_to_catalogue_pandas = add_ww3_to_catalogue
add_ww3_to_catalogue_polars = add_ww3_to_catalogue