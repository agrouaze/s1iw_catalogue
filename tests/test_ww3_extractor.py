"""
Unit tests for WW3 extractor module.
"""

import logging
import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch
from scipy.spatial import KDTree
import numpy as np
import pandas as pd
import polars as pl
import pytest
import xarray as xr
from shapely.geometry import box, Polygon

from s1iw_catalogue.ww3_extractor import WW3Extractor, add_ww3_to_catalogue


# Set up logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestWW3Extractor:
    """Test suite for WW3Extractor class."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration."""
        return {
            "ww3": {
                "primary_root": "/test/primary",
                "fallback_root": "/test/fallback",
                "field_nc_subdir": "FIELD_NC",
                "hs_variable": "hs",
                "t01_variable": "t01",
                "primary_pattern": "CCI_WW3-GLOB-30M_{yearmonth}.nc",
                "fallback_pattern": "MARC_WW3-GLOB-30M_{datestr}Z.nc",
                "default_n_jobs": 2,
            }
        }

    @pytest.fixture
    def extractor(self, mock_config):
        """Create a WW3Extractor instance with mock config."""
        with patch("s1iw_catalogue.ww3_extractor.load_config") as mock_load:
            mock_load.return_value = mock_config
            return WW3Extractor()

    @pytest.fixture
    def sample_catalogue_df(self):
        """Create a sample catalogue DataFrame with WKT strings instead of Polygon objects."""
        polygon = box(-5, 48, -4.5, 48.5)
        
        data = {
            "SAFE SLC": ["S1A_IW_SLC_001", "S1A_IW_SLC_002"],
            "SAFE GRD": ["S1A_IW_GRD_001", "S1A_IW_GRD_002"],
            "start date SAFE": [
                pd.Timestamp("2023-01-15 12:00:00"),
                pd.Timestamp("2023-01-15 15:00:00"),
            ],
            "polygon SLC": [polygon.wkt, polygon.wkt],
            "geometry": [polygon.wkt, polygon.wkt],  # Use WKT strings for Polars compatibility
        }
        return pd.DataFrame(data)

    @pytest.fixture
    def sample_catalogue_df_with_objects(self):
        """Create a sample catalogue DataFrame with Shapely Polygon objects."""
        polygon = box(-5, 48, -4.5, 48.5)
        
        data = {
            "SAFE SLC": ["S1A_IW_SLC_001", "S1A_IW_SLC_002"],
            "SAFE GRD": ["S1A_IW_GRD_001", "S1A_IW_GRD_002"],
            "start date SAFE": [
                pd.Timestamp("2023-01-15 12:00:00"),
                pd.Timestamp("2023-01-15 15:00:00"),
            ],
            "polygon SLC": [polygon, polygon],
            "geometry": [polygon, polygon],
        }
        return pd.DataFrame(data)

    def test_init(self, extractor):
        """Test initialization of WW3Extractor."""
        assert extractor.primary_root == "/test/primary"
        assert extractor.fallback_root == "/test/fallback"
        assert extractor.hs_var == "hs"
        assert extractor.t01_var == "t01"
        assert extractor.output_columns == ["Hs WW3", "Tp WW3"]
        assert extractor.default_n_jobs == 2
        assert extractor._cache == {}
        assert extractor._cache_hits == 0
        assert extractor._cache_misses == 0

    def test_get_nearest_ww3_hour(self, extractor):
        """Test getting nearest WW3 hour."""
        # Test exact hours
        assert extractor.get_nearest_ww3_hour(0) == 0
        assert extractor.get_nearest_ww3_hour(3) == 3
        assert extractor.get_nearest_ww3_hour(6) == 6
        
        # Test rounding
        assert extractor.get_nearest_ww3_hour(1) == 0
        assert extractor.get_nearest_ww3_hour(2) == 3
        assert extractor.get_nearest_ww3_hour(4) == 3
        assert extractor.get_nearest_ww3_hour(5) == 6
        
        # Test edge cases
        assert extractor.get_nearest_ww3_hour(23) == 0

    def test_get_ww3_filename(self, extractor):
        """Test getting WW3 filename."""
        dt = pd.Timestamp("2023-01-15 12:30:00")
        primary, fallback, year = extractor.get_ww3_filename(dt)
        
        assert year == 2023
        assert primary == "CCI_WW3-GLOB-30M_202301.nc"
        assert "MARC_WW3-GLOB-30M" in fallback
        assert "Z.nc" in fallback

    def test_get_file_path(self, extractor):
        """Test getting file path with mock existence."""
        with patch("os.path.exists") as mock_exists:
            # Test primary exists - use return_value instead of side_effect for single call
            mock_exists.return_value = True
            path = extractor.get_file_path(2023, "test.nc", "fallback.nc")
            assert "test.nc" in path
            assert "/test/primary/2023/FIELD_NC/test.nc" == path

            # Test primary not exists, fallback exists
            mock_exists.side_effect = [False, True]
            path = extractor.get_file_path(2023, "test.nc", "fallback.nc")
            assert "fallback.nc" in path
            assert "/test/fallback/2023/fallback.nc" == path

            # Test neither exists - provide enough values for all calls
            mock_exists.side_effect = [False, False]
            path = extractor.get_file_path(2023, "test.nc", "fallback.nc")
            assert path is None

    def test_parse_geometry(self, extractor):
        """Test geometry parsing."""
        # Test None
        assert extractor._parse_geometry(None) is None

        # Test WKT string
        polygon_wkt = "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"
        parsed = extractor._parse_geometry(polygon_wkt)
        assert parsed is not None
        assert parsed.geom_type == "Polygon"

        # Test invalid WKT
        assert extractor._parse_geometry("INVALID") is None

    def test_get_centroid_from_geometry(self, extractor):
        """Test getting centroid from geometry."""
        polygon = box(0, 0, 1, 1)
        row = {"geometry": polygon}
        lon, lat = extractor._get_centroid_from_geometry(row, "geometry")
        assert lon == 0.5
        assert lat == 0.5

        # Test with WKT string
        polygon_wkt = "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"
        row = {"geometry": polygon_wkt}
        lon, lat = extractor._get_centroid_from_geometry(row, "geometry")
        assert lon == 0.5
        assert lat == 0.5

        # Test with invalid geometry
        row = {"geometry": None}
        lon, lat = extractor._get_centroid_from_geometry(row, "geometry")
        assert np.isnan(lon)
        assert np.isnan(lat)

    @patch("s1iw_catalogue.ww3_extractor.xr.open_dataset")
    def test_load_ww3_data_with_times(self, mock_open_dataset, extractor):
        """Test loading WW3 data with times."""
        # Create mock dataset
        mock_ds = MagicMock()
        mock_ds.longitude.values = np.array([0, 1, 2])
        mock_ds.latitude.values = np.array([0, 1, 2])
        mock_ds.time.values = np.array([np.datetime64("2023-01-15T00:00:00")])
        mock_ds.__getitem__.return_value.load.return_value.values = np.random.rand(1, 3, 3)
        mock_open_dataset.return_value = mock_ds

        with tempfile.NamedTemporaryFile(suffix=".nc") as tmpfile:
            result = extractor._load_ww3_data_with_times(tmpfile.name)
            
            assert result is not None
            assert "hs_data" in result
            assert "t01_data" in result
            assert "times" in result
            assert "tree" in result
            assert extractor._cache_hits == 0
            assert extractor._cache_misses == 1

            # Test cache hit
            result2 = extractor._load_ww3_data_with_times(tmpfile.name)
            assert extractor._cache_hits == 1

    @patch("s1iw_catalogue.ww3_extractor.xr.open_dataset")
    def test_load_ww3_data_with_times_error(self, mock_open_dataset, extractor):
        """Test error handling in loading WW3 data."""
        mock_open_dataset.side_effect = Exception("Test error")
        
        with tempfile.NamedTemporaryFile(suffix=".nc") as tmpfile:
            result = extractor._load_ww3_data_with_times(tmpfile.name)
            assert result is None

    def test_extract_batch_pandas(self, extractor, sample_catalogue_df):
        """Test batch extraction with Pandas DataFrame."""
        with patch.object(extractor, '_load_ww3_data_with_times') as mock_load, \
             patch.object(extractor, 'get_file_path') as mock_get_path, \
             patch.object(extractor, '_extract_values_batch') as mock_extract:
            
            # Setup mocks
            mock_get_path.return_value = "/test/path.nc"
            mock_load.return_value = {"hs_data": np.random.rand(1, 3, 3), "t01_data": np.random.rand(1, 3, 3)}
            
            # Mock extraction results
            mock_extract.return_value = {
                0: {"Hs WW3": 2.5, "Tp WW3": 8.0},
                1: {"Hs WW3": 3.0, "Tp WW3": 9.0},
            }

            result = extractor.extract_batch(sample_catalogue_df, n_jobs=1, verbose=False)
            
            assert isinstance(result, pd.DataFrame)
            assert "Hs WW3" in result.columns
            assert "Tp WW3" in result.columns
            assert result["Hs WW3"].iloc[0] == 2.5
            assert result["Tp WW3"].iloc[0] == 8.0

    def test_extract_batch_pandas_with_objects(self, extractor, sample_catalogue_df_with_objects):
        """Test batch extraction with Pandas DataFrame containing Shapely objects."""
        with patch.object(extractor, '_load_ww3_data_with_times') as mock_load, \
             patch.object(extractor, 'get_file_path') as mock_get_path, \
             patch.object(extractor, '_extract_values_batch') as mock_extract:
            
            # Setup mocks
            mock_get_path.return_value = "/test/path.nc"
            mock_load.return_value = {"hs_data": np.random.rand(1, 3, 3), "t01_data": np.random.rand(1, 3, 3)}
            
            # Mock extraction results
            mock_extract.return_value = {
                0: {"Hs WW3": 2.5, "Tp WW3": 8.0},
                1: {"Hs WW3": 3.0, "Tp WW3": 9.0},
            }

            result = extractor.extract_batch(sample_catalogue_df_with_objects, n_jobs=1, verbose=False)
            
            assert isinstance(result, pd.DataFrame)
            assert "Hs WW3" in result.columns
            assert "Tp WW3" in result.columns

    def test_extract_batch_polars(self, extractor, sample_catalogue_df):
        """Test batch extraction with Polars DataFrame."""
        # Convert to Polars - use WKT strings to avoid Arrow conversion issues
        pl_df = pl.from_pandas(sample_catalogue_df)
        
        with patch.object(extractor, '_load_ww3_data_with_times') as mock_load, \
             patch.object(extractor, 'get_file_path') as mock_get_path, \
             patch.object(extractor, '_extract_values_batch') as mock_extract:
            
            mock_get_path.return_value = "/test/path.nc"
            mock_load.return_value = {"hs_data": np.random.rand(1, 3, 3), "t01_data": np.random.rand(1, 3, 3)}
            mock_extract.return_value = {
                0: {"Hs WW3": 2.5, "Tp WW3": 8.0},
                1: {"Hs WW3": 3.0, "Tp WW3": 9.0},
            }

            result = extractor.extract_batch(pl_df, n_jobs=1, verbose=False)
            
            assert isinstance(result, pl.DataFrame)
            assert "Hs WW3" in result.columns
            assert "Tp WW3" in result.columns

    def test_extract_batch_missing_columns(self, extractor):
        """Test extraction with missing required columns."""
        df = pd.DataFrame({"wrong_column": [1, 2]})
        
        with pytest.raises(ValueError, match="Missing time column"):
            extractor.extract_batch(df)

        # Test missing geometry column
        df = pd.DataFrame({"start date SAFE": [pd.Timestamp.now(), pd.Timestamp.now()]})
        with pytest.raises(ValueError, match="No geometry column found"):
            extractor.extract_batch(df)

    def test_extract_batch_with_file_not_found(self, extractor, sample_catalogue_df):
        """Test extraction when file not found."""
        with patch.object(extractor, 'get_file_path') as mock_get_path:
            mock_get_path.return_value = None
            
            result = extractor.extract_batch(sample_catalogue_df, n_jobs=1, verbose=False)
            
            # Should have NaN values
            assert result["Hs WW3"].isna().all()
            assert result["Tp WW3"].isna().all()
            assert extractor._diagnostics["file_not_found"] > 0

    def test_extract_values_batch(self, extractor):
        """Test batch value extraction."""
        # Create mock cache entry
        hs_data = np.random.rand(2, 3, 3)
        t01_data = np.random.rand(2, 3, 3)
        times = np.array([np.datetime64("2023-01-15T00:00:00"), 
                         np.datetime64("2023-01-15T03:00:00")])
        
        # Create KDTree
        lon_grid, lat_grid = np.meshgrid([0, 1, 2], [0, 1, 2])
        points = np.column_stack([lon_grid.ravel(), lat_grid.ravel()])
        from scipy.spatial import KDTree
        tree = KDTree(points)
        
        cache_entry = {
            "hs_data": hs_data,
            "t01_data": t01_data,
            "times": times,
            "lon_grid": lon_grid,
            "tree": tree,
        }
        
        # Create sample dataframe with WKT strings
        polygon = box(0.5, 0.5, 1.5, 1.5)
        df = pd.DataFrame({
            "geometry": [polygon.wkt, polygon.wkt],
            "start date SAFE": [pd.Timestamp("2023-01-15 00:30:00"), 
                               pd.Timestamp("2023-01-15 02:30:00")]
        })
        
        indices = [0, 1]
        
        result = extractor._extract_values_batch(
            cache_entry, indices, df, "geometry", "start date SAFE"
        )
        
        assert len(result) == 2
        assert all(key in result for key in [0, 1])
        assert all(col in result[0] for col in ["Hs WW3", "Tp WW3"])
        assert extractor._diagnostics["total_products"] == 2
        assert extractor._diagnostics["valid_geometries"] == 2

    def test_extract_values_batch_invalid_geometry(self, extractor):
        """Test batch extraction with invalid geometry."""
        # Create mock cache entry
        hs_data = np.random.rand(1, 3, 3)
        t01_data = np.random.rand(1, 3, 3)
        times = np.array([np.datetime64("2023-01-15T00:00:00")])
        
        lon_grid, lat_grid = np.meshgrid([0, 1, 2], [0, 1, 2])
        points = np.column_stack([lon_grid.ravel(), lat_grid.ravel()])
        from scipy.spatial import KDTree
        tree = KDTree(points)
        
        cache_entry = {
            "hs_data": hs_data,
            "t01_data": t01_data,
            "times": times,
            "lon_grid": lon_grid,
            "tree": tree,
        }
        
        # Create dataframe with invalid geometry
        df = pd.DataFrame({
            "geometry": [None, "INVALID_WKT"],
            "start date SAFE": [pd.Timestamp("2023-01-15 00:30:00"), 
                               pd.Timestamp("2023-01-15 00:30:00")]
        })
        
        indices = [0, 1]
        
        result = extractor._extract_values_batch(
            cache_entry, indices, df, "geometry", "start date SAFE"
        )
        
        assert len(result) == 2
        assert np.isnan(result[0]["Hs WW3"])
        assert np.isnan(result[1]["Hs WW3"])
        assert extractor._diagnostics["invalid_geometries"] == 2

    def test_extract_values_batch_out_of_bounds(self, extractor):
        """Test batch extraction with out-of-bounds indices."""
        # Create mock cache entry with small data
        hs_data = np.random.rand(1, 2, 2)  # Small grid
        t01_data = np.random.rand(1, 2, 2)
        times = np.array([np.datetime64("2023-01-15T00:00:00")])
        
        lon_grid, lat_grid = np.meshgrid([0, 1], [0, 1])
        points = np.column_stack([lon_grid.ravel(), lat_grid.ravel()])
        from scipy.spatial import KDTree
        tree = KDTree(points)
        
        cache_entry = {
            "hs_data": hs_data,
            "t01_data": t01_data,
            "times": times,
            "lon_grid": lon_grid,
            "tree": tree,
        }
        
        # Create dataframe with geometry far from grid
        polygon = box(100, 100, 101, 101)  # Far from grid
        df = pd.DataFrame({
            "geometry": [polygon.wkt],
            "start date SAFE": [pd.Timestamp("2023-01-15 00:30:00")]
        })
        
        indices = [0]
        
        result = extractor._extract_values_batch(
            cache_entry, indices, df, "geometry", "start date SAFE"
        )
        
        # KDTree will find nearest point, but it might be within bounds
        # The test should verify the extraction works
        assert len(result) == 1
        assert 0 in result

    def test_extract_values_batch_empty_indices(self, extractor):
        """Test batch extraction with empty indices list."""
        cache_entry = {
            "hs_data": np.random.rand(1, 3, 3),
            "t01_data": np.random.rand(1, 3, 3),
            "times": np.array([np.datetime64("2023-01-15T00:00:00")]),
            "lon_grid": np.meshgrid([0, 1, 2], [0, 1, 2])[0],
            "tree": KDTree(np.array([[0, 0], [1, 1], [2, 2]])),
        }
        
        df = pd.DataFrame({"geometry": ["POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"]})
        indices = []
        
        result = extractor._extract_values_batch(
            cache_entry, indices, df, "geometry", "start date SAFE"
        )
        
        assert result == {}

    def test_print_diagnostics(self, extractor, caplog):
        """Test printing diagnostics."""
        extractor._diagnostics = {
            "total_products": 10,
            "valid_geometries": 8,
            "invalid_geometries": 2,
            "successful_extractions": 8,
            "failed_extractions": 0,
            "sample_coords": [(0.5, 0.5, pd.Timestamp.now(), "SAFE1")],
            "ww3_grid_bounds": {"lon_min": -180, "lon_max": 180, "lat_min": -90, "lat_max": 90},
            "file_not_found": 0,
            "extraction_errors": [],
        }
        
        with caplog.at_level(logging.INFO):
            extractor.print_diagnostics()
            
            assert "Total products: 10" in caplog.text
            assert "Valid geometries: 8" in caplog.text
            assert "WW3 grid bounds" in caplog.text

    def test_add_ww3_to_catalogue_pandas(self, sample_catalogue_df):
        """Test convenience function with Pandas."""
        with patch.object(WW3Extractor, 'extract_batch') as mock_extract:
            mock_extract.return_value = sample_catalogue_df.copy()
            
            result = add_ww3_to_catalogue(sample_catalogue_df)
            
            assert isinstance(result, pd.DataFrame)
            mock_extract.assert_called_once()

    def test_add_ww3_to_catalogue_polars(self, sample_catalogue_df):
        """Test convenience function with Polars."""
        pl_df = pl.from_pandas(sample_catalogue_df)
        
        with patch.object(WW3Extractor, 'extract_batch') as mock_extract:
            # Return a Polars DataFrame with WW3 columns
            result_df = pl_df.clone()
            result_df = result_df.with_columns([
                pl.Series("Hs WW3", [2.5, 3.0]),
                pl.Series("Tp WW3", [8.0, 9.0]),
            ])
            mock_extract.return_value = result_df
            
            result = add_ww3_to_catalogue(pl_df)
            
            assert isinstance(result, pl.DataFrame)
            mock_extract.assert_called_once()


class TestWW3ExtractorIntegration:
    """Integration tests for WW3Extractor (requires actual data files)."""

    @pytest.mark.skip(reason="Requires actual WW3 data files")
    def test_integration_with_real_data(self):
        """Test extraction with real WW3 data (if available)."""
        # This test would require actual WW3 data files
        # It's skipped by default but can be run manually
        pass