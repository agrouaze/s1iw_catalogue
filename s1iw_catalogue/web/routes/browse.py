"""Browse API routes for filtering and exploring catalogue content."""

from typing import Any, Optional, List
import logging
import traceback

import numpy as np
import polars as pl
import shapely
from fastapi import APIRouter, HTTPException, Response, status
from scipy.stats import gaussian_kde
from shapely import wkt
from shapely.geometry import mapping

from s1iw_catalogue.web.models import FilterRequest, HeatmapRequest, MapRequest
from s1iw_catalogue.web.utils.data_loader import catalogue_manager
from s1iw_catalogue.web.routes.responses import (
    FILTER_RESPONSES,
    EXPORT_RESPONSES,
    MAP_RESPONSES,
    HEATMAP_RESPONSES,
    WIND_HEATMAP_RESPONSES,
    COUNTS_RESPONSES,
    TIMESERIES_RESPONSES,
    MONTHLY_TIMESERIES_RESPONSES,
    METADATA_RESPONSES,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Helper Functions
# ============================================================================

def _apply_filter(
    df: pl.DataFrame,
    filter_value: Any,
    column: str,
    filter_type: str = "contains",
) -> pl.DataFrame:
    """
    Generic filter application with different types.
    
    Args:
        df: DataFrame to filter
        filter_value: Value to filter by
        column: Column name to filter on
        filter_type: Type of filter - "contains", "in", "gte", "lte", "presence", "dataset"
    
    Returns:
        Filtered DataFrame
    """
    # Skip if filter value is None or empty
    if filter_value is None:
        return df
    
    if column not in df.columns:
        return df
    
    # Handle empty lists/strings
    if isinstance(filter_value, (list, str)) and len(filter_value) == 0:
        return df
    
    try:
        if filter_type == "contains":
            return df.filter(pl.col(column).str.contains(filter_value))
        elif filter_type == "in":
            return df.filter(pl.col(column).is_in(filter_value))
        elif filter_type == "gte":
            return df.filter(pl.col(column) >= filter_value)
        elif filter_type == "lte":
            return df.filter(pl.col(column) <= filter_value)
        elif filter_type == "presence":
            if filter_value:
                return df.filter(pl.col(column).is_not_null())
            else:
                return df.filter(pl.col(column).is_null())
        elif filter_type == "dataset":
            condition = pl.lit(False)
            for dataset in filter_value:
                condition = condition | pl.col(column).list.contains(dataset)
            return df.filter(condition)
        else:
            logger.warning("Unknown filter type: %s", filter_type)
            return df
    except Exception as e:
        logger.exception("Error applying filter on column %s: %s", column, e)
        raise


def apply_filters(df: pl.DataFrame, filter_req: FilterRequest) -> pl.DataFrame:
    """
    Apply all filters to catalogue DataFrame.
    
    Args:
        df: Input DataFrame
        filter_req: Filter request object
    
    Returns:
        Filtered DataFrame
    """
    try:
        # Define filter configurations: (value, column, filter_type)
        filters = [
            (filter_req.slc_name, "SAFE SLC", "contains"),
            (filter_req.grd_name, "SAFE GRD", "contains"),
            (filter_req.ocn_name, "SAFE OCN", "contains"),
            (filter_req.datasets, "datasets", "dataset"),
            (filter_req.polarization, "polarization", "in"),
            (filter_req.satellites, "unit", "in"),
            (filter_req.date_start, "start date SAFE", "gte"),
            (filter_req.date_end, "start date SAFE", "lte"),
            (filter_req.has_slc, "PATH SLC", "presence"),
            (filter_req.has_grd, "PATH GRD", "presence"),
            (filter_req.has_ocn, "PATH OCN", "presence"),
            (filter_req.has_l1b, "PATH L1B XSP A21", "presence"),
            (filter_req.has_l1c, "PATH L1C XSP B17", "presence"),
        ]
        
        # Apply all filters
        for value, column, filter_type in filters:
            df = _apply_filter(df, value, column, filter_type)
        
        return df
        
    except Exception as e:
        logger.exception("Error in apply_filters: %s", e)
        raise


# ============================================================================
# API Routes
# ============================================================================

@router.post(
    "/filter",
    responses=FILTER_RESPONSES,
    status_code=status.HTTP_200_OK
)
async def filter_catalogue(request: FilterRequest) -> dict[str, Any]:
    """
    Filter catalogue entries based on criteria.
    
    Args:
        request: FilterRequest containing all filter parameters
    
    Returns:
        Filtered catalogue entries with pagination
    
    Raises:
        HTTPException: 503 if catalogue not loaded, 500 on internal error
    """
    try:
        if not catalogue_manager.is_loaded():
            raise HTTPException(status_code=503, detail="Catalogue not loaded")

        logger.info("Filter request: datasets=%s", request.datasets)
        logger.info("Filter request: polarization=%s", request.polarization)
        logger.info("Filter request: satellites=%s", request.satellites)

        df = apply_filters(catalogue_manager.df, request)

        columns = [
            "SAFE SLC",
            "SAFE GRD",
            "SAFE OCN",
            "datasets",
            "start date SAFE",
            "horodating",
            "polarization",
            "unit",
        ]
        columns = [c for c in columns if c in df.columns]

        result_df = df.select(columns).slice(request.offset, request.limit)

        return {
            "total": df.height,
            "limit": request.limit,
            "offset": request.offset,
            "rows": result_df.to_dicts(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in filter_catalogue: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/export",
    responses=EXPORT_RESPONSES,
    status_code=status.HTTP_200_OK
)
async def export_catalogue(request: FilterRequest) -> Response:
    """
    Export filtered catalogue as CSV with selected columns.
    
    Args:
        request: FilterRequest containing filter parameters and column selection
    
    Returns:
        CSV file as a Response
    
    Raises:
        HTTPException: 400 if no valid columns, 404 if no data, 
                      413 if too many rows, 503 if catalogue not loaded
    """
    try:
        if not catalogue_manager.is_loaded():
            raise HTTPException(status_code=503, detail="Catalogue not loaded")

        # Hard limit to avoid large exports
        max_export_rows = 10000

        df = apply_filters(catalogue_manager.df, request)

        if df.height == 0:
            raise HTTPException(
                status_code=404, detail="No data found for the selected filters"
            )

        if df.height > max_export_rows:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Too many rows ({df.height}). Please refine your filters. "
                    f"Maximum allowed: {max_export_rows}"
                ),
            )

        # Use requested columns or default to all
        if request.columns and len(request.columns) > 0:
            selected_cols = [c for c in request.columns if c in df.columns]
            if not selected_cols:
                raise HTTPException(
                    status_code=400, detail="No valid columns selected for export"
                )
            df = df.select(selected_cols)
        else:
            # Default: all columns except large geometry columns (optional)
            exclude = ["polygon SLC", "polygon GRD"]
            selected_cols = [c for c in df.columns if c not in exclude]
            df = df.select(selected_cols)

        # Convert list columns to strings for CSV export
        list_cols = [c for c in df.columns if df[c].dtype == pl.List(pl.Utf8)]
        for col in list_cols:
            df = df.with_columns(pl.col(col).list.join(", ").alias(col))
        
        # Convert Polars DataFrame to CSV
        csv_data = df.write_csv()
        csv_bytes = csv_data.encode("utf-8")

        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=catalogue_export.csv"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in export_catalogue: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/map",
    responses=MAP_RESPONSES,
    status_code=status.HTTP_200_OK
)
async def get_map_data(request: MapRequest) -> dict[str, Any]:
    """
    Get product data with geometry for map visualization.
    
    Returns polygons (simplified if many features).
    
    Args:
        request: MapRequest containing filter and max_polygons parameters
    
    Returns:
        GeoJSON FeatureCollection
    
    Raises:
        HTTPException: 503 if catalogue not loaded, 500 on internal error
    """
    try:
        if not catalogue_manager.is_loaded():
            raise HTTPException(status_code=503, detail="Catalogue not loaded")

        df = apply_filters(catalogue_manager.df, request.filter)

        max_polygons = request.max_polygons or 500
        df = df.slice(0, max_polygons)

        features = []
        polygon_count = 0

        for row in df.to_dicts():
            polygon_wkt = row.get("polygon SLC") or row.get("polygon GRD")
            if not polygon_wkt:
                continue

            try:
                geom = wkt.loads(polygon_wkt)
                if geom.geom_type == "MultiPolygon":
                    geom = shapely.ops.unary_union(geom)

                tolerance = 0.02 if df.height > 100 else 0.01
                geom = geom.simplify(tolerance)
                polygon_count += 1

                feature = {
                    "type": "Feature",
                    "geometry": mapping(geom),
                    "properties": {
                        "safe_slc": row.get("SAFE SLC"),
                        "safe_grd": row.get("SAFE GRD"),
                        "safe_ocn": row.get("SAFE OCN"),
                        "dataset": row.get("datasets"),
                        "polarization": row.get("polarization"),
                        "satellite": row.get("unit"),
                        "start_date": (
                            str(row.get("start date SAFE"))
                            if row.get("start date SAFE")
                            else None
                        ),
                        "horodating": (
                            str(row.get("horodating")) if row.get("horodating") else None
                        ),
                    },
                }
                features.append(feature)
            except Exception as e:
                logger.warning("Error processing geometry for row: %s", e)
                continue

        return {
            "type": "FeatureCollection",
            "features": features,
            "total": df.height,
            "polygon_count": polygon_count,
            "is_point_mode": False,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in get_map_data: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/heatmap/hs_tp",
    responses=HEATMAP_RESPONSES,
    status_code=status.HTTP_200_OK
)
async def get_hs_tp_heatmap(request: HeatmapRequest) -> dict[str, Any]:
    """
    Get Hs/Tp data with density estimation.
    
    Args:
        request: HeatmapRequest containing filter parameters
    
    Returns:
        Heatmap data with Hs, Tp values and density estimates
    
    Raises:
        HTTPException: 503 if catalogue not loaded, 500 on internal error
    """
    try:
        if not catalogue_manager.is_loaded():
            raise HTTPException(status_code=503, detail="Catalogue not loaded")

        df = apply_filters(catalogue_manager.df, request.filter)

        hs_tp_df = df.filter(pl.col("Hs WW3").is_finite() & pl.col("Tp WW3").is_finite())

        if hs_tp_df.height == 0:
            return {
                "data": [],
                "message": "No valid Hs/Tp data available for the selected filters",
            }

        hs = hs_tp_df["Hs WW3"].to_numpy()
        tp = hs_tp_df["Tp WW3"].to_numpy()

        mask = ~np.isnan(hs) & ~np.isnan(tp)
        hs = hs[mask]
        tp = tp[mask]

        if len(hs) < 2:
            return {
                "data": {"hs": hs.tolist(), "tp": tp.tolist(), "density": [1.0] * len(hs)},
                "count": len(hs),
            }

        data = np.vstack([hs, tp])
        kde = gaussian_kde(data)
        density = kde(data)

        density_norm = density / density.max() if density.max() > 0 else density

        return {
            "data": {
                "hs": hs.tolist(),
                "tp": tp.tolist(),
                "density": density_norm.tolist(),
            },
            "count": len(hs),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in get_hs_tp_heatmap: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/heatmap/wind",
    responses=WIND_HEATMAP_RESPONSES,
    status_code=status.HTTP_200_OK
)
async def get_wind_heatmap(request: HeatmapRequest) -> dict[str, Any]:
    """
    Get wind direction/speed data with density estimation.
    
    Args:
        request: HeatmapRequest containing filter parameters
    
    Returns:
        Wind heatmap data with speed, direction and density estimates
    
    Raises:
        HTTPException: 503 if catalogue not loaded, 500 on internal error
    """
    try:
        if not catalogue_manager.is_loaded():
            raise HTTPException(status_code=503, detail="Catalogue not loaded")

        df = apply_filters(catalogue_manager.df, request.filter)

        wind_df = df.filter(
            pl.col("U10 ecmwf").is_finite() & pl.col("V10 ecmwf").is_finite()
        )

        if wind_df.height == 0:
            return {
                "data": [],
                "message": "No valid wind data available for the selected filters",
            }

        wind_df = wind_df.with_columns(
            [
                ((pl.col("U10 ecmwf") ** 2 + pl.col("V10 ecmwf") ** 2).sqrt()).alias(
                    "wind_speed"
                ),
                (
                    (
                        180
                        + (180 / np.pi)
                        * pl.arctan2(pl.col("U10 ecmwf"), pl.col("V10 ecmwf"))
                    )
                    % 360
                ).alias("wind_direction"),
            ]
        )

        directions = wind_df["wind_direction"].to_numpy()
        speeds = wind_df["wind_speed"].to_numpy()
        mask = ~np.isnan(directions) & ~np.isnan(speeds)
        directions = directions[mask]
        speeds = speeds[mask]

        if len(speeds) < 2:
            return {
                "data": {
                    "speed": speeds.tolist(),
                    "direction": directions.tolist(),
                    "density": [1.0] * len(speeds),
                },
                "count": len(speeds),
            }

        data = np.vstack([directions, speeds])
        kde = gaussian_kde(data)
        density = kde(data)
        density_norm = density / density.max() if density.max() > 0 else density

        return {
            "data": {
                "speed": speeds.tolist(),
                "direction": directions.tolist(),
                "density": density_norm.tolist(),
            },
            "count": len(speeds),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in get_wind_heatmap: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/category_counts",
    responses=COUNTS_RESPONSES,
    status_code=status.HTTP_200_OK
)
async def get_category_counts(request: FilterRequest) -> dict[str, Any]:
    """
    Get counts of products per category.
    
    Args:
        request: FilterRequest containing filter parameters
    
    Returns:
        Dictionary with category counts and total
    
    Raises:
        HTTPException: 503 if catalogue not loaded, 500 on internal error
    """
    try:
        if not catalogue_manager.is_loaded():
            raise HTTPException(status_code=503, detail="Catalogue not loaded")

        df = apply_filters(catalogue_manager.df, request)

        if "category" not in df.columns:
            return {"counts": {}, "total": df.height}

        counts_df = df.group_by("category").agg(pl.len())
        counts = dict(zip(counts_df["category"], counts_df["len"]))

        return {"counts": counts, "total": df.height}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in get_category_counts: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/daily_counts",
    responses=TIMESERIES_RESPONSES,
    status_code=status.HTTP_200_OK
)
async def get_daily_counts(request: FilterRequest) -> dict[str, Any]:
    """
    Get daily product counts per dataset for stacked bar chart.
    
    Args:
        request: FilterRequest containing filter parameters
    
    Returns:
        Daily time series data grouped by dataset
    
    Raises:
        HTTPException: 503 if catalogue not loaded, 500 on internal error
    """
    try:
        if not catalogue_manager.is_loaded():
            raise HTTPException(status_code=503, detail="Catalogue not loaded")

        df = apply_filters(catalogue_manager.df, request)

        if "start date SAFE" not in df.columns or "datasets" not in df.columns:
            return {"error": "Missing required columns"}

        df = df.with_columns(pl.col("start date SAFE").dt.date().alias("date"))

        exploded = df.explode("datasets")
        counts = exploded.group_by(["date", "datasets"]).agg(pl.len())

        pivot = counts.pivot(
            index="date", columns="datasets", values="len", aggregate_function="sum"
        )
        pivot = pivot.fill_null(0)

        dates = pivot["date"].to_list()
        dataset_names = [c for c in pivot.columns if c != "date"]
        series = {ds: pivot[ds].to_list() for ds in dataset_names}

        sorted_indices = sorted(range(len(dates)), key=lambda i: dates[i])
        dates_sorted = [dates[i] for i in sorted_indices]
        series_sorted = {
            ds: [series[ds][i] for i in sorted_indices] for ds in dataset_names
        }

        return {
            "dates": dates_sorted,
            "series": series_sorted,
            "datasets": dataset_names,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in get_daily_counts: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/monthly_counts",
    responses=MONTHLY_TIMESERIES_RESPONSES,
    status_code=status.HTTP_200_OK
)
async def get_monthly_counts(request: FilterRequest) -> dict[str, Any]:
    """
    Get monthly product counts per dataset for stacked bar chart.
    
    Args:
        request: FilterRequest containing filter parameters
    
    Returns:
        Monthly time series data grouped by dataset
    
    Raises:
        HTTPException: 503 if catalogue not loaded, 500 on internal error
    """
    try:
        if not catalogue_manager.is_loaded():
            raise HTTPException(status_code=503, detail="Catalogue not loaded")

        df = apply_filters(catalogue_manager.df, request)

        if "start date SAFE" not in df.columns or "datasets" not in df.columns:
            return {"error": "Missing required columns"}

        df = df.with_columns(pl.col("start date SAFE").dt.truncate("1mo").alias("month"))

        exploded = df.explode("datasets")
        counts = exploded.group_by(["month", "datasets"]).agg(pl.len())

        pivot = counts.pivot(
            index="month", columns="datasets", values="len", aggregate_function="sum"
        )
        pivot = pivot.fill_null(0)

        months = pivot["month"].to_list()
        dataset_names = [c for c in pivot.columns if c != "month"]
        series = {ds: pivot[ds].to_list() for ds in dataset_names}

        sorted_indices = sorted(range(len(months)), key=lambda i: months[i])
        months_sorted = [months[i] for i in sorted_indices]
        series_sorted = {
            ds: [series[ds][i] for i in sorted_indices] for ds in dataset_names
        }

        month_labels = [m.strftime("%Y-%m") for m in months_sorted]

        return {
            "months": month_labels,
            "series": series_sorted,
            "datasets": dataset_names,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in get_monthly_counts: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get(
    "/datasets_metadata",
    responses=METADATA_RESPONSES,
    status_code=status.HTTP_200_OK
)
async def get_datasets_metadata() -> dict[str, Any]:
    """
    Get metadata for all datasets with counts.
    
    Returns:
        Dictionary containing dataset metadata and debug information
    
    Raises:
        HTTPException: 503 if catalogue not loaded, 500 on internal error
    """
    try:
        if not catalogue_manager.is_loaded():
            raise HTTPException(status_code=503, detail="Catalogue not loaded")

        df = catalogue_manager.df
        metadata = catalogue_manager.get_dataset_metadata() or {}

        debug = {
            "has_datasets_col": "datasets" in df.columns,
            "dtype": str(df["datasets"].dtype) if "datasets" in df.columns else "absent",
            "sample": df["datasets"].head(2).to_list() if "datasets" in df.columns else [],
            "non_empty_rows": (
                df.filter(pl.col("datasets").is_not_null()).height
                if "datasets" in df.columns
                else 0
            ),
            "metadata_keys": list(metadata.keys()),
        }

        counts = {}
        if "datasets" in df.columns and df["datasets"].dtype == pl.List(pl.Utf8):
            exploded = df.explode("datasets")
            counts_df = exploded.group_by("datasets").agg(pl.len())
            counts = dict(zip(counts_df["datasets"], counts_df["len"]))

        result = {}
        for ds_name, meta in metadata.items():
            result[ds_name] = {
                "description": meta.get("description", ""),
                "category": meta.get("category", ""),
                "type": meta.get("type", ""),
                "count": counts.get(ds_name, 0),
            }

        for ds_name, count in counts.items():
            if ds_name not in result:
                result[ds_name] = {
                    "description": "",
                    "category": "",
                    "type": "",
                    "count": count,
                }

        return {"metadata": result, "debug": debug}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in get_datasets_metadata: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e