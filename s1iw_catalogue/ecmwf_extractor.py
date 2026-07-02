"""ECMWF Wind Data Extractor for Sentinel-1 products.

Optimized: Load ECMWF variables into memory once, then access as numpy arrays.
Handles two distinct archives: Primary (0.1°, hourly) and Fallback (0.125°, 3-hourly).
"""

from __future__ import annotations

import logging
import os
import time
import warnings
from functools import wraps
from typing import Any, Union

import numpy as np
import pandas as pd
import polars as pl
import xarray as xr
from joblib import Parallel, delayed
from scipy.spatial import KDTree
from shapely import wkt
from tqdm import tqdm

from s1iw_catalogue.schema import ECMWF_COLUMNS

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)


def timing_decorator(func: Any) -> Any:
    """Decorator to log execution time of functions."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
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

    def load_config(config_path: str | None = None) -> dict[str, Any]:
        """Fallback config loader if module is not installed."""
        import yaml

        if config_path is None:
            possible_paths = [
                os.path.join(os.path.dirname(__file__), "..", "config", "config.yml"),
                os.path.join(os.path.dirname(__file__), "config.yml"),
                os.path.join(os.getcwd(), "config.yml"),
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    config_path = path
                    break
        if not config_path or not os.path.exists(config_path):
            raise FileNotFoundError("Config file not found")
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)


class ECMWFExtractor:
    """Extract ECMWF 10m wind data with numpy array access."""

    def __init__(self, config_path: str | None = None) -> None:
        self.config = load_config(config_path)
        ecmwf_config = self.config.get("ecmwf", {})

        self.switch_date = pd.to_datetime(
            ecmwf_config.get("switch_date", "2019-08-21T00:00:00")
        )

        self.primary_cfg = ecmwf_config.get("primary", {})
        self.fallback_cfg = ecmwf_config.get("fallback", {})

        self.output_columns = ECMWF_COLUMNS
        self.default_n_jobs = ecmwf_config.get("default_n_jobs", 6)

        # Cache: store loaded numpy arrays directly
        self._cache: dict[str, dict[str, Any]] = {}
        self._cache_hits = 0
        self._cache_misses = 0

        self._diagnostics: dict[str, Any] = {
            "total_products": 0,
            "valid_geometries": 0,
            "invalid_geometries": 0,
            "successful_extractions": 0,
            "failed_extractions": 0,
            "file_not_found": 0,
        }

    def _get_doy(self, dt: pd.Timestamp) -> str:
        """Get the 3-digit day of the year for fallback path formatting."""
        return f"{dt.dayofyear:03d}"

    @timing_decorator
    def get_file_path(self, dt: pd.Timestamp) -> tuple[str | None, bool]:
        """
        Resolve the absolute file path for a given datetime.

        Args:
            dt: The target datetime for extraction

        Returns:
            A tuple containing (file_path or None, is_fallback_bool)
        """
        is_fallback = dt < self.switch_date
        cfg = self.fallback_cfg if is_fallback else self.primary_cfg

        datestr = dt.strftime(cfg["datestr_format"])
        filename = cfg["pattern"].format(datestr=datestr)

        # Both primary and fallback use the YYYY/DOY/ directory structure
        doy = self._get_doy(dt)
        filepath = os.path.join(cfg["root"], str(dt.year), doy, filename)

        if os.path.exists(filepath):
            return filepath, is_fallback

        logger.warning(f"ECMWF file not found: {filepath}")
        return None, is_fallback

    @timing_decorator
    def _parse_geometry(self, geom: Any) -> Any:
        """Parse WKT string or shapely geometry to a Polygon."""
        if geom is None:
            return None
        if hasattr(geom, "geom_type"):
            return geom
        if isinstance(geom, str):
            try:
                geom_obj = wkt.loads(geom.strip())
                if geom_obj.geom_type == "MultiPolygon":
                    areas = [p.area for p in geom_obj.geoms]
                    geom_obj = geom_obj.geoms[np.argmax(areas)]
                if geom_obj.geom_type == "Polygon":
                    return geom_obj
            except Exception:
                pass
        return None

    def _get_centroid_from_geometry(
        self, row: pd.Series, geom_col: str
    ) -> tuple[float, float]:
        """Extract centroid (lon, lat) from a geometry column."""
        geom = row[geom_col]
        if geom is None:
            return np.nan, np.nan
        try:
            parsed = self._parse_geometry(geom)
            if parsed is not None and hasattr(parsed, "centroid"):
                return parsed.centroid.x, parsed.centroid.y
        except Exception:
            pass
        return np.nan, np.nan

    @timing_decorator
    def _load_ecmwf_data(
        self, filepath: str, is_fallback: bool
    ) -> dict[str, Any] | None:
        """
        Load ECMWF data into memory as numpy arrays.

        Handles structural differences between Primary (3D) and Fallback (4D).

        Args:
            filepath: Path to the NetCDF file
            is_fallback: Flag to apply fallback-specific processing

        Returns:
            Dictionary containing numpy arrays and KDTree, or None if failed
        """
        if filepath in self._cache:
            self._cache_hits += 1
            return self._cache[filepath]

        self._cache_misses += 1
        logger.debug(f"  Loading {os.path.basename(filepath)} into memory...")

        try:
            # ds = xr.open_dataset(filepath, engine="h5netcdf")
            # Do not force h5netcdf: the netcdf4 engine is much more robust
            # for ECMWF formats and avoids "file signature not found" errors
            # on network filesystems (Lustre/NFS) or classic NetCDF4 files.
            ds = xr.open_dataset(filepath)
            # Handle case-insensitive coordinate names
            lat_name = "latitude" if "latitude" in ds else "Latitude"
            lon_name = "longitude" if "longitude" in ds else "Longitude"

            lons = ds[lon_name].values
            lats = ds[lat_name].values
            times = ds.time.values
            
            # Fix 0-360 longitude convention (common in ECMWF/GFS)
            # Convert to -180-180 standard geographic coordinates to match Shapely WKT centroids
            if np.max(lons) > 180:
                lons = np.where(lons > 180, lons - 360, lons)
                
            lon_grid, lat_grid = np.meshgrid(lons, lats)

            # Build KDTree
            points = np.column_stack([lon_grid.ravel(), lat_grid.ravel()])
            tree = KDTree(points)

            # Get variable names and fill values based on source
            cfg = self.fallback_cfg if is_fallback else self.primary_cfg
            u_var = cfg["u_var"]
            v_var = cfg["v_var"]
            fill_val = cfg["fill_value"]

            u_data = ds[u_var].values
            v_data = ds[v_var].values

            # Fallback NetCDF is 4D (time, height, lat, lon). Squeeze height dim.
            if is_fallback and u_data.ndim == 4:
                u_data = u_data[:, 0, :, :]
                v_data = v_data[:, 0, :, :]

            # Replace NetCDF fill values with numpy NaN
            u_data = u_data.astype(np.float32)
            v_data = v_data.astype(np.float32)
            u_data[u_data == fill_val] = np.nan
            v_data[v_data == fill_val] = np.nan

            ds.close()

            cache_entry = {
                "u_data": u_data,
                "v_data": v_data,
                "times": times,
                "lon_grid": lon_grid,
                "lat_grid": lat_grid,
                "tree": tree,
            }
            self._cache[filepath] = cache_entry
            return cache_entry

        except Exception as e:
            logger.error(f"Failed to load {filepath}: {e}")
            return None

    @timing_decorator
    def _extract_values_batch(
        self,
        cache_entry: dict[str, Any],
        indices: list[int],
        df_with_info: pd.DataFrame,
        geom_col: str,
        time_col: str = "start date SAFE",
    ) -> dict[int, dict[str, float]]:
        """
        Extract U10/V10 values using numpy array access.

        Args:
            cache_entry: Dictionary with pre-loaded data and tree
            indices: Pandas indices to process
            df_with_info: DataFrame containing geometries and times
            geom_col: Name of the geometry column
            time_col: Name of the time column

        Returns:
            Dictionary mapping original index to extracted values
        """
        results: dict[int, dict[str, float]] = {}

        u_data = cache_entry["u_data"]
        v_data = cache_entry["v_data"]
        times = cache_entry["times"]
        tree = cache_entry["tree"]
        lon_grid = cache_entry["lon_grid"]

        centroids = []
        time_indices = []
        valid_indices = []

        for idx in indices:
            row = df_with_info.loc[idx]
            lon, lat = self._get_centroid_from_geometry(row, geom_col)

            self._diagnostics["total_products"] += 1

            if np.isnan(lon) or np.isnan(lat):
                self._diagnostics["invalid_geometries"] += 1
                results[idx] = {col: np.nan for col in self.output_columns}
                continue

            # Find closest time in the dataset
            try:
                product_time = pd.to_datetime(row[time_col])
                time_idx = np.argmin(np.abs(times - np.datetime64(product_time)))
            except Exception:
                time_idx = 0

            self._diagnostics["valid_geometries"] += 1
            centroids.append((lon, lat))
            time_indices.append(time_idx)
            valid_indices.append(idx)

        if not valid_indices:
            return results

        # Batch KDTree query
        centroids_array = np.array(centroids)
        distances, indices_kd = tree.query(centroids_array, k=1)

        # Convert to lat/lon indices
        ilats, ilons = np.unravel_index(indices_kd, lon_grid.shape)
        # Extract values using numpy array indexing
        for i, idx in enumerate(valid_indices):
            ilat = ilats[i]
            ilon = ilons[i]
            time_idx = time_indices[i]

            if (
                time_idx >= u_data.shape[0]
                or ilat >= u_data.shape[1]
                or ilon >= u_data.shape[2]
            ):
                results[idx] = {col: np.nan for col in self.output_columns}
                continue

            u_val = float(u_data[time_idx, ilat, ilon])
            v_val = float(v_data[time_idx, ilat, ilon])

            self._diagnostics["successful_extractions"] += 1

            results[idx] = {
                "U10 ecmwf": u_val,
                "V10 ecmwf": v_val,
            }

        return results

    @timing_decorator
    def extract_batch(
        self,
        catalogue_df: Union[pd.DataFrame, pl.DataFrame],
        n_jobs: int | None = None,
        verbose: bool = True,
    ) -> Union[pd.DataFrame, pl.DataFrame]:
        """
        Extract ECMWF data for a catalogue DataFrame.

        Args:
            catalogue_df: Input catalogue (Pandas or Polars)
            n_jobs: Number of parallel workers
            verbose: Enable progress bars and info logs

        Returns:
            DataFrame with extracted U10 and V10 columns
        """
        total_start = time.time()

        self._diagnostics = {
            "total_products": 0,
            "valid_geometries": 0,
            "invalid_geometries": 0,
            "successful_extractions": 0,
            "failed_extractions": 0,
            "file_not_found": 0,
        }

        is_polars = isinstance(catalogue_df, pl.DataFrame)
        if is_polars:
            catalogue_df = catalogue_df.to_pandas()

        if n_jobs is None:
            n_jobs = self.default_n_jobs

        time_col = "start date SAFE" if "start date SAFE" in catalogue_df.columns else "start_date"
        if time_col not in catalogue_df.columns:
            raise ValueError("Missing time column")

        geom_col = next(
            (col for col in ["polygon SLC", "polygon GRD", "geometry"] if col in catalogue_df.columns),
            None,
        )
        if geom_col is None:
            raise ValueError("No geometry column found")

        # Resolve file paths for each row
        def resolve_path(row: pd.Series) -> pd.Series:
            try:
                dt = pd.to_datetime(row[time_col])
                filepath, is_fb = self.get_file_path(dt)
                row["_ecmwf_path"] = filepath
                row["_ecmwf_is_fallback"] = is_fb
            except Exception:
                row["_ecmwf_path"] = None
                row["_ecmwf_is_fallback"] = False
            return row

        if verbose:
            logger.info(f"🌬️ Resolving ECMWF paths for {len(catalogue_df)} products...")
        df_with_info = catalogue_df.apply(resolve_path, axis=1)

        # Group by file path for efficient batch loading
        groups: dict[str, dict[str, Any]] = {}
        for idx, row in df_with_info.iterrows():
            key = row["_ecmwf_path"]
            if key is None:
                self._diagnostics["file_not_found"] += 1
                # Populate NaN for missing files directly
                for col in self.output_columns:
                    catalogue_df.loc[idx, col] = np.nan
                continue
            
            if key not in groups:
                groups[key] = {
                    "is_fallback": row["_ecmwf_is_fallback"],
                    "indices": [],
                }
            groups[key]["indices"].append(idx)

        if verbose:
            logger.info(f"📊 Processing {len(groups)} ECMWF files...")

        def process_group(group_info: dict[str, Any]) -> dict[int, dict[str, float]]:
            """Process a single file for a group of indices."""
            indices = group_info["indices"]
            is_fb = group_info["is_fallback"]
            
            cache_entry = self._load_ecmwf_data(str(group_info["__key__"]), is_fb)
            if cache_entry is None:
                return {idx: {col: np.nan for col in self.output_columns} for idx in indices}
            
            return self._extract_values_batch(cache_entry, indices, df_with_info, geom_col, time_col)

        # Process groups (inject key for the closure)
        group_list = [{"__key__": k, **v} for k, v in groups.items()]
        
        if n_jobs > 1 and len(group_list) > 0:
            all_results = Parallel(n_jobs=n_jobs, verbose=0)(
                delayed(process_group)(info)
                for info in tqdm(group_list, desc="Processing ECMWF", disable=not verbose)
            )
        else:
            all_results = []
            for info in tqdm(group_list, desc="Processing ECMWF", disable=not verbose):
                all_results.append(process_group(info))

        # Merge results back to DataFrame
        for result_dict in all_results:
            for idx, vals in result_dict.items():
                for col, val in vals.items():
                    catalogue_df.loc[idx, col] = val

        if verbose:
            logger.info(f"🏁 ECMWF extraction total time: {time.time() - total_start:.3f}s")
            logger.info(f"   Cache: hits={self._cache_hits}, misses={self._cache_misses}")

        if is_polars:
            return pl.from_pandas(catalogue_df)
        return catalogue_df


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def add_ecmwf_to_catalogue(
    catalogue_df: Union[pd.DataFrame, pl.DataFrame],
    config_path: str | None = None,
    n_jobs: int = 6,
    verbose: bool = True,
) -> Union[pd.DataFrame, pl.DataFrame]:
    """
    Convenience function to add ECMWF wind data to a catalogue.

    Args:
        catalogue_df: Pandas or Polars catalogue DataFrame
        config_path: Path to the configuration file
        n_jobs: Number of parallel workers
        verbose: Enable logging

    Returns:
        Updated DataFrame with ECMWF columns
    """
    extractor = ECMWFExtractor(config_path)
    return extractor.extract_batch(catalogue_df, n_jobs=n_jobs, verbose=verbose)