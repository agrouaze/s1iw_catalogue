"""Unit tests for browse.py routes."""

import json
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import polars as pl
import pytest
import shapely.ops
from fastapi import HTTPException, Response
from shapely import wkt
from shapely.geometry import MultiPolygon, box, mapping

from s1iw_catalogue.web.models import FilterRequest, HeatmapRequest, MapRequest
from s1iw_catalogue.web.routes.browse import (
    _apply_filter,
    apply_filters,
    export_catalogue,
    filter_catalogue,
    get_category_counts,
    get_daily_counts,
    get_datasets_metadata,
    get_hs_tp_heatmap,
    get_map_data,
    get_monthly_counts,
    get_wind_heatmap,
)
from s1iw_catalogue.web.utils.data_loader import catalogue_manager


@pytest.fixture
def mock_catalogue_df():
    """Create a mock catalogue DataFrame."""
    polygon = box(-5, 48, -4.5, 48.5)

    return pl.DataFrame(
        {
            "SAFE SLC": ["S1A_IW_SLC_001", "S1A_IW_SLC_002", None, "S1A_IW_SLC_004"],
            "SAFE GRD": [None, None, "S1A_IW_GRD_001", "S1A_IW_GRD_002"],
            "SAFE OCN": [None, "S1A_IW_OCN_001", None, "S1A_IW_OCN_002"],
            "datasets": [["SLC"], ["SLC", "GRD"], ["GRD"], ["SLC", "GRD", "OCN"]],
            "start date SAFE": [
                datetime(2023, 1, 15, 12, 0, 0),
                datetime(2023, 1, 16, 12, 0, 0),
                datetime(2023, 1, 15, 12, 0, 0),
                datetime(2023, 1, 17, 12, 0, 0),
            ],
            "horodating": [datetime.now()] * 4,
            "polarization": ["VV", "VH", "VV", "VH"],
            "unit": ["S1A", "S1A", "S1B", "S1B"],
            "polygon SLC": [polygon.wkt, polygon.wkt, None, polygon.wkt],
            "polygon GRD": [None, None, polygon.wkt, polygon.wkt],
            "PATH SLC": ["/path/slc1", "/path/slc2", None, "/path/slc4"],
            "PATH GRD": [None, None, "/path/grd1", "/path/grd2"],
            "PATH OCN": [None, "/path/ocn1", None, "/path/ocn2"],
            "PATH L1B XSP A21": [None, None, "/path/l1b", None],
            "PATH L1C XSP B17": [None, None, None, "/path/l1c"],
            "category": ["SAR", "SAR", "SAR", "OCEAN"],
            "Hs WW3": [2.5, np.nan, 3.0, 1.8],
            "Tp WW3": [8.0, np.nan, 9.5, 7.0],
            "U10 ecmwf": [5.2, np.nan, 4.8, 6.1],
            "V10 ecmwf": [3.1, np.nan, 2.9, 3.8],
        }
    )


@pytest.fixture
def mock_catalogue_manager(mock_catalogue_df):
    """Mock the catalogue_manager."""
    with patch("s1iw_catalogue.web.routes.browse.catalogue_manager") as mock_manager:
        mock_manager.df = mock_catalogue_df
        mock_manager.is_loaded.return_value = True
        mock_manager.get_dataset_metadata.return_value = {
            "SLC": {"description": "SLC products", "category": "SAR", "type": "SLC"},
            "GRD": {"description": "GRD products", "category": "SAR", "type": "GRD"},
            "OCN": {"description": "OCN products", "category": "OCEAN", "type": "OCN"},
        }
        yield mock_manager


class TestApplyFilter:
    """Test the _apply_filter helper function."""

    def test_apply_filter_contains(self, mock_catalogue_df):
        """Test contains filter."""
        result = _apply_filter(mock_catalogue_df, "SLC_001", "SAFE SLC", "contains")
        assert result.height == 1
        assert result["SAFE SLC"][0] == "S1A_IW_SLC_001"

    def test_apply_filter_in(self, mock_catalogue_df):
        """Test in filter."""
        result = _apply_filter(mock_catalogue_df, ["VV", "VH"], "polarization", "in")
        assert result.height == 4  # All rows have VV or VH

    def test_apply_filter_gte(self, mock_catalogue_df):
        """Test gte filter."""
        result = _apply_filter(
            mock_catalogue_df, datetime(2023, 1, 16), "start date SAFE", "gte"
        )
        assert result.height == 2  # Rows from Jan 16 and 17

    def test_apply_filter_lte(self, mock_catalogue_df):
        """Test lte filter."""
        result = _apply_filter(
            mock_catalogue_df,
            datetime(2023, 1, 16, 23, 59, 59),
            "start date SAFE",
            "lte",
        )
        # This should include Jan 15 (2 rows) and Jan 16 (1 row) = 3 rows total
        # But if the filter is using the exact datetime comparison, we need to be careful
        # Let's check what we actually get
        assert result.height == 3  # Rows on Jan 15 (2 rows) + Jan 16 (1 row)

    def test_apply_filter_presence_true(self, mock_catalogue_df):
        """Test presence filter with True."""
        result = _apply_filter(mock_catalogue_df, True, "PATH SLC", "presence")
        assert result.height == 3  # 3 rows have PATH SLC

    def test_apply_filter_presence_false(self, mock_catalogue_df):
        """Test presence filter with False."""
        result = _apply_filter(mock_catalogue_df, False, "PATH SLC", "presence")
        assert result.height == 1  # 1 row doesn't have PATH SLC

    def test_apply_filter_dataset(self, mock_catalogue_df):
        """Test dataset filter."""
        result = _apply_filter(mock_catalogue_df, ["GRD"], "datasets", "dataset")
        assert result.height == 3  # 3 rows have GRD

    def test_apply_filter_none_value(self, mock_catalogue_df):
        """Test filter with None value (should return original)."""
        result = _apply_filter(mock_catalogue_df, None, "SAFE SLC", "contains")
        assert result.height == mock_catalogue_df.height

    def test_apply_filter_column_not_exists(self, mock_catalogue_df):
        """Test filter with non-existent column."""
        result = _apply_filter(mock_catalogue_df, "test", "non_existent", "contains")
        assert result.height == mock_catalogue_df.height

    def test_apply_filter_unknown_type(self, mock_catalogue_df):
        """Test filter with unknown type."""
        result = _apply_filter(mock_catalogue_df, "test", "SAFE SLC", "unknown")
        assert result.height == mock_catalogue_df.height

    def test_apply_filter_empty_list(self, mock_catalogue_df):
        """Test filter with empty list."""
        result = _apply_filter(mock_catalogue_df, [], "SAFE SLC", "contains")
        assert result.height == mock_catalogue_df.height


class TestApplyFilters:
    """Test the apply_filters function."""

    def test_apply_filters_all(self, mock_catalogue_df):
        """Test applying multiple filters."""
        filter_req = FilterRequest(
            slc_name="SLC_001",
            datasets=["SLC"],
            polarization=["VV"],
        )
        result = apply_filters(mock_catalogue_df, filter_req)
        assert result.height == 1
        assert result["SAFE SLC"][0] == "S1A_IW_SLC_001"

    def test_apply_filters_with_has_slc(self, mock_catalogue_df):
        """Test filter with has_slc."""
        filter_req = FilterRequest(has_slc=True)
        result = apply_filters(mock_catalogue_df, filter_req)
        assert result.height == 3

    def test_apply_filters_with_has_grd(self, mock_catalogue_df):
        """Test filter with has_grd."""
        filter_req = FilterRequest(has_grd=True)
        result = apply_filters(mock_catalogue_df, filter_req)
        assert result.height == 2

    def test_apply_filters_with_has_l1b(self, mock_catalogue_df):
        """Test filter with has_l1b."""
        filter_req = FilterRequest(has_l1b=True)
        result = apply_filters(mock_catalogue_df, filter_req)
        assert result.height == 1

    def test_apply_filters_with_has_l1c(self, mock_catalogue_df):
        """Test filter with has_l1c."""
        filter_req = FilterRequest(has_l1c=True)
        result = apply_filters(mock_catalogue_df, filter_req)
        assert result.height == 1

    def test_apply_filters_with_date_range(self, mock_catalogue_df):
        """Test filter with date range."""
        filter_req = FilterRequest(
            date_start=datetime(2023, 1, 16, 0, 0, 0),
            date_end=datetime(2023, 1, 16, 23, 59, 59),
        )
        result = apply_filters(mock_catalogue_df, filter_req)
        # Only rows with start date SAFE on Jan 16
        assert result.height == 1

    def test_apply_filters_with_satellites(self, mock_catalogue_df):
        """Test filter with satellites."""
        filter_req = FilterRequest(satellites=["S1A"])
        result = apply_filters(mock_catalogue_df, filter_req)
        assert result.height == 2


@pytest.mark.asyncio
class TestFilterCatalogue:
    """Test the filter_catalogue endpoint."""

    async def test_filter_catalogue_success(self, mock_catalogue_manager):
        """Test successful catalogue filtering."""
        request = FilterRequest(offset=0, limit=10)
        result = await filter_catalogue(request)

        assert "total" in result
        assert "rows" in result
        assert result["limit"] == 10
        assert result["offset"] == 0

    async def test_filter_catalogue_not_loaded(self, mock_catalogue_manager):
        """Test filtering when catalogue is not loaded."""
        mock_catalogue_manager.is_loaded.return_value = False
        request = FilterRequest()

        with pytest.raises(HTTPException) as exc:
            await filter_catalogue(request)
        assert exc.value.status_code == 503

    async def test_filter_catalogue_error(self, mock_catalogue_manager):
        """Test filtering with error."""
        mock_catalogue_manager.df = None  # Cause error
        request = FilterRequest()

        with pytest.raises(HTTPException) as exc:
            await filter_catalogue(request)
        assert exc.value.status_code == 500


@pytest.mark.asyncio
class TestExportCatalogue:
    """Test the export_catalogue endpoint."""

    async def test_export_catalogue_success(self, mock_catalogue_manager):
        """Test successful export."""
        request = FilterRequest()
        response = await export_catalogue(request)

        assert isinstance(response, Response)
        assert response.media_type == "text/csv"
        assert (
            "attachment; filename=catalogue_export.csv"
            in response.headers["Content-Disposition"]
        )

    async def test_export_catalogue_with_columns(self, mock_catalogue_manager):
        """Test export with specific columns."""
        request = FilterRequest(columns=["SAFE SLC", "datasets"])
        response = await export_catalogue(request)

        assert isinstance(response, Response)
        csv_content = response.body.decode("utf-8")
        assert "SAFE SLC" in csv_content
        assert "datasets" in csv_content

    async def test_export_catalogue_not_loaded(self, mock_catalogue_manager):
        """Test export when catalogue is not loaded."""
        mock_catalogue_manager.is_loaded.return_value = False
        request = FilterRequest()

        with pytest.raises(HTTPException) as exc:
            await export_catalogue(request)
        assert exc.value.status_code == 503

    async def test_export_catalogue_no_data(self, mock_catalogue_manager):
        """Test export with no data."""
        mock_catalogue_manager.df = pl.DataFrame(
            {
                "SAFE SLC": [],
                "SAFE GRD": [],
            }
        )
        request = FilterRequest()

        with pytest.raises(HTTPException) as exc:
            await export_catalogue(request)
        assert exc.value.status_code == 404

    async def test_export_catalogue_too_many_rows(self, mock_catalogue_manager):
        """Test export with too many rows."""
        # Create a DataFrame with more than 10000 rows
        large_df = pl.DataFrame(
            {
                "SAFE SLC": [f"S1A_IW_SLC_{i:05d}" for i in range(10001)],
                "SAFE GRD": [f"S1A_IW_GRD_{i:05d}" for i in range(10001)],
            }
        )
        mock_catalogue_manager.df = large_df
        request = FilterRequest()

        with pytest.raises(HTTPException) as exc:
            await export_catalogue(request)
        assert exc.value.status_code == 413

    async def test_export_catalogue_invalid_columns(self, mock_catalogue_manager):
        """Test export with invalid columns."""
        request = FilterRequest(columns=["INVALID_COLUMN"])

        with pytest.raises(HTTPException) as exc:
            await export_catalogue(request)
        assert exc.value.status_code == 400


@pytest.mark.asyncio
class TestGetMapData:
    """Test the get_map_data endpoint."""

    async def test_get_map_data_success(self, mock_catalogue_manager):
        """Test successful map data retrieval."""
        request = MapRequest(filter=FilterRequest())
        result = await get_map_data(request)

        assert result["type"] == "FeatureCollection"
        assert "features" in result
        assert result["total"] > 0
        assert result["is_point_mode"] is False

    async def test_get_map_data_not_loaded(self, mock_catalogue_manager):
        """Test map data when catalogue is not loaded."""
        mock_catalogue_manager.is_loaded.return_value = False
        request = MapRequest(filter=FilterRequest())

        with pytest.raises(HTTPException) as exc:
            await get_map_data(request)
        assert exc.value.status_code == 503

    async def test_get_map_data_with_max_polygons(self, mock_catalogue_manager):
        """Test map data with max_polygons limit."""
        request = MapRequest(filter=FilterRequest(), max_polygons=2)
        result = await get_map_data(request)

        assert len(result["features"]) <= 2

    async def test_get_map_data_with_multipolygon(self, mock_catalogue_manager):
        """Test map data with MultiPolygon geometry."""
        # Create a MultiPolygon
        poly1 = box(-5, 48, -4.5, 48.5)
        poly2 = box(-4.5, 48.5, -4, 49)
        multi_poly = MultiPolygon([poly1, poly2])

        # Use WKT string for the polygon column
        df = pl.DataFrame(
            {
                "SAFE SLC": ["S1A_IW_SLC_001"],
                "polygon SLC": [multi_poly.wkt],
                "polygon GRD": [None],
                "datasets": [["SLC"]],
                "polarization": ["VV"],
                "unit": ["S1A"],
                "start date SAFE": [datetime(2023, 1, 15)],
                "horodating": [datetime.now()],
            }
        )
        mock_catalogue_manager.df = df

        # Mock shapely.ops.unary_union to avoid import issues
        with patch("shapely.ops.unary_union", return_value=multi_poly):
            request = MapRequest(filter=FilterRequest())
            result = await get_map_data(request)

        assert len(result["features"]) == 1
        assert result["polygon_count"] == 1

    async def test_get_map_data_with_invalid_geometry(self, mock_catalogue_manager):
        """Test map data with invalid geometry."""
        df = pl.DataFrame(
            {
                "SAFE SLC": ["S1A_IW_SLC_001"],
                "polygon SLC": ["INVALID_WKT"],
                "polygon GRD": [None],
                "datasets": [["SLC"]],
                "polarization": ["VV"],
                "unit": ["S1A"],
                "start date SAFE": [datetime(2023, 1, 15)],
                "horodating": [datetime.now()],
            }
        )
        mock_catalogue_manager.df = df

        request = MapRequest(filter=FilterRequest())
        result = await get_map_data(request)

        assert len(result["features"]) == 0


@pytest.mark.asyncio
class TestHeatmapEndpoints:
    """Test the heatmap endpoints."""

    async def test_get_hs_tp_heatmap_success(self, mock_catalogue_manager):
        """Test successful Hs/Tp heatmap."""
        # HeatmapRequest requires a 'variable' field
        request = HeatmapRequest(
            filter=FilterRequest(), variable="Hs WW3"  # Add the required variable field
        )
        result = await get_hs_tp_heatmap(request)

        assert "data" in result
        assert "count" in result
        assert result["count"] > 0
        assert "hs" in result["data"]
        assert "tp" in result["data"]
        assert "density" in result["data"]

    async def test_get_hs_tp_heatmap_no_data(self, mock_catalogue_manager):
        """Test Hs/Tp heatmap with no valid data."""
        df = pl.DataFrame(
            {
                "Hs WW3": [np.nan, np.nan],
                "Tp WW3": [np.nan, np.nan],
                "SAFE SLC": ["test1", "test2"],
                "start date SAFE": [datetime.now(), datetime.now()],
            }
        )
        mock_catalogue_manager.df = df

        request = HeatmapRequest(filter=FilterRequest(), variable="Hs WW3")
        result = await get_hs_tp_heatmap(request)

        assert "message" in result
        assert result["data"] == []

    async def test_get_hs_tp_heatmap_not_loaded(self, mock_catalogue_manager):
        """Test Hs/Tp heatmap when catalogue is not loaded."""
        mock_catalogue_manager.is_loaded.return_value = False
        request = HeatmapRequest(filter=FilterRequest(), variable="Hs WW3")

        with pytest.raises(HTTPException) as exc:
            await get_hs_tp_heatmap(request)
        assert exc.value.status_code == 503

    async def test_get_hs_tp_heatmap_single_point(self, mock_catalogue_manager):
        """Test Hs/Tp heatmap with single data point."""
        df = pl.DataFrame(
            {
                "Hs WW3": [2.5],
                "Tp WW3": [8.0],
                "SAFE SLC": ["test1"],
                "start date SAFE": [datetime.now()],
            }
        )
        mock_catalogue_manager.df = df

        request = HeatmapRequest(filter=FilterRequest(), variable="Hs WW3")
        result = await get_hs_tp_heatmap(request)

        assert result["count"] == 1
        assert len(result["data"]["density"]) == 1

    async def test_get_wind_heatmap_success(self, mock_catalogue_manager):
        """Test successful wind heatmap."""
        request = HeatmapRequest(
            filter=FilterRequest(), variable="wind"  # Add the required variable field
        )
        result = await get_wind_heatmap(request)

        assert "data" in result
        assert "count" in result
        assert result["count"] > 0
        assert "speed" in result["data"]
        assert "direction" in result["data"]
        assert "density" in result["data"]

    async def test_get_wind_heatmap_no_data(self, mock_catalogue_manager):
        """Test wind heatmap with no valid data."""
        df = pl.DataFrame(
            {
                "U10 ecmwf": [np.nan, np.nan],
                "V10 ecmwf": [np.nan, np.nan],
                "SAFE SLC": ["test1", "test2"],
                "start date SAFE": [datetime.now(), datetime.now()],
            }
        )
        mock_catalogue_manager.df = df

        request = HeatmapRequest(filter=FilterRequest(), variable="wind")
        result = await get_wind_heatmap(request)

        assert "message" in result
        assert result["data"] == []

    async def test_get_wind_heatmap_not_loaded(self, mock_catalogue_manager):
        """Test wind heatmap when catalogue is not loaded."""
        mock_catalogue_manager.is_loaded.return_value = False
        request = HeatmapRequest(filter=FilterRequest(), variable="wind")

        with pytest.raises(HTTPException) as exc:
            await get_wind_heatmap(request)
        assert exc.value.status_code == 503

    async def test_get_wind_heatmap_single_point(self, mock_catalogue_manager):
        """Test wind heatmap with single data point."""
        df = pl.DataFrame(
            {
                "U10 ecmwf": [5.2],
                "V10 ecmwf": [3.1],
                "SAFE SLC": ["test1"],
                "start date SAFE": [datetime.now()],
            }
        )
        mock_catalogue_manager.df = df

        request = HeatmapRequest(filter=FilterRequest(), variable="wind")
        result = await get_wind_heatmap(request)

        assert result["count"] == 1
        assert len(result["data"]["density"]) == 1


@pytest.mark.asyncio
class TestCategoryCounts:
    """Test the category_counts endpoint."""

    async def test_get_category_counts_success(self, mock_catalogue_manager):
        """Test successful category counts."""
        request = FilterRequest()
        result = await get_category_counts(request)

        assert "counts" in result
        assert "total" in result
        assert "SAR" in result["counts"]
        assert "OCEAN" in result["counts"]

    async def test_get_category_counts_no_category(self, mock_catalogue_manager):
        """Test category counts when category column doesn't exist."""
        df = pl.DataFrame(
            {
                "SAFE SLC": ["S1A_IW_SLC_001"],
                "datasets": [["SLC"]],
            }
        )
        mock_catalogue_manager.df = df

        request = FilterRequest()
        result = await get_category_counts(request)

        assert result["counts"] == {}
        assert result["total"] == 1

    async def test_get_category_counts_not_loaded(self, mock_catalogue_manager):
        """Test category counts when catalogue is not loaded."""
        mock_catalogue_manager.is_loaded.return_value = False
        request = FilterRequest()

        with pytest.raises(HTTPException) as exc:
            await get_category_counts(request)
        assert exc.value.status_code == 503


@pytest.mark.asyncio
class TestDailyCounts:
    """Test the daily_counts endpoint."""

    async def test_get_daily_counts_success(self, mock_catalogue_manager):
        """Test successful daily counts."""
        request = FilterRequest()
        result = await get_daily_counts(request)

        assert "dates" in result
        assert "series" in result
        assert "datasets" in result
        assert len(result["dates"]) > 0

    async def test_get_daily_counts_missing_columns(self, mock_catalogue_manager):
        """Test daily counts with missing columns."""
        df = pl.DataFrame(
            {
                "SAFE SLC": ["S1A_IW_SLC_001"],
            }
        )
        mock_catalogue_manager.df = df

        request = FilterRequest()
        result = await get_daily_counts(request)

        assert "error" in result

    async def test_get_daily_counts_not_loaded(self, mock_catalogue_manager):
        """Test daily counts when catalogue is not loaded."""
        mock_catalogue_manager.is_loaded.return_value = False
        request = FilterRequest()

        with pytest.raises(HTTPException) as exc:
            await get_daily_counts(request)
        assert exc.value.status_code == 503


@pytest.mark.asyncio
class TestMonthlyCounts:
    """Test the monthly_counts endpoint."""

    async def test_get_monthly_counts_success(self, mock_catalogue_manager):
        """Test successful monthly counts."""
        request = FilterRequest()
        result = await get_monthly_counts(request)

        assert "months" in result
        assert "series" in result
        assert "datasets" in result
        assert len(result["months"]) > 0

    async def test_get_monthly_counts_missing_columns(self, mock_catalogue_manager):
        """Test monthly counts with missing columns."""
        df = pl.DataFrame(
            {
                "SAFE SLC": ["S1A_IW_SLC_001"],
            }
        )
        mock_catalogue_manager.df = df

        request = FilterRequest()
        result = await get_monthly_counts(request)

        assert "error" in result

    async def test_get_monthly_counts_not_loaded(self, mock_catalogue_manager):
        """Test monthly counts when catalogue is not loaded."""
        mock_catalogue_manager.is_loaded.return_value = False
        request = FilterRequest()

        with pytest.raises(HTTPException) as exc:
            await get_monthly_counts(request)
        assert exc.value.status_code == 503


@pytest.mark.asyncio
class TestDatasetsMetadata:
    """Test the datasets_metadata endpoint."""

    async def test_get_datasets_metadata_success(self, mock_catalogue_manager):
        """Test successful datasets metadata retrieval."""
        result = await get_datasets_metadata()

        assert "metadata" in result
        assert "debug" in result
        assert "SLC" in result["metadata"]
        assert result["metadata"]["SLC"]["description"] == "SLC products"

    async def test_get_datasets_metadata_not_loaded(self, mock_catalogue_manager):
        """Test datasets metadata when catalogue is not loaded."""
        mock_catalogue_manager.is_loaded.return_value = False

        with pytest.raises(HTTPException) as exc:
            await get_datasets_metadata()
        assert exc.value.status_code == 503

    async def test_get_datasets_metadata_no_datasets_col(self, mock_catalogue_manager):
        """Test datasets metadata when datasets column doesn't exist."""
        # Create a DataFrame without datasets column
        df = pl.DataFrame(
            {
                "SAFE SLC": ["S1A_IW_SLC_001"],
                "category": ["SAR"],
            }
        )
        mock_catalogue_manager.df = df
        # Mock metadata to return empty
        mock_catalogue_manager.get_dataset_metadata.return_value = {}

        result = await get_datasets_metadata()

        assert result["debug"]["has_datasets_col"] is False
        assert result["metadata"] == {}

    async def test_get_datasets_metadata_error(self, mock_catalogue_manager):
        """Test datasets metadata with error."""
        mock_catalogue_manager.get_dataset_metadata.side_effect = Exception(
            "Test error"
        )

        with pytest.raises(HTTPException) as exc:
            await get_datasets_metadata()
        assert exc.value.status_code == 500
