"""Browse API routes for filtering and exploring catalogue content."""

from typing import Any, Dict, List, Optional

import json
import logging
import traceback

import polars as pl
import shapely
from fastapi import APIRouter, HTTPException
from shapely import wkt
from shapely.geometry import Point, mapping, shape
import numpy as np
from scipy.stats import gaussian_kde
from s1iw_catalogue.web.models import FilterRequest, HeatmapRequest, MapRequest
from s1iw_catalogue.web.utils.data_loader import catalogue_manager

logger = logging.getLogger(__name__)
router = APIRouter()


def apply_filters(df: pl.DataFrame, filter_req: FilterRequest) -> pl.DataFrame:
    """Apply filters to catalogue DataFrame."""
    try:
        # SAFE name filters (partial match)
        if filter_req.slc_name:
            if "SAFE SLC" in df.columns:
                df = df.filter(pl.col("SAFE SLC").str.contains(filter_req.slc_name))

        if filter_req.grd_name:
            if "SAFE GRD" in df.columns:
                df = df.filter(pl.col("SAFE GRD").str.contains(filter_req.grd_name))

        if filter_req.ocn_name:
            if "SAFE OCN" in df.columns:
                df = df.filter(pl.col("SAFE OCN").str.contains(filter_req.ocn_name))

        # Dataset filter - check if any selected dataset is in the list
        if filter_req.datasets and len(filter_req.datasets) > 0:
            if "datasets" in df.columns:
                # Use list.contains with any() to check overlap
                # Create a condition: for any dataset in the list, check if it's in the array
                # Polars: list.contains(element) returns a boolean expression
                # We need to check if ANY of the selected datasets are in the list
                condition = pl.lit(False)
                for dataset in filter_req.datasets:
                    condition = condition | pl.col("datasets").list.contains(dataset)
                df = df.filter(condition)

        # Polarization filter
        if filter_req.polarization and len(filter_req.polarization) > 0:
            if "polarization" in df.columns:
                df = df.filter(pl.col("polarization").is_in(filter_req.polarization))

        # Satellite filter
        if filter_req.satellites and len(filter_req.satellites) > 0:
            if "unit" in df.columns:
                df = df.filter(pl.col("unit").is_in(filter_req.satellites))

        # Date range filters
        if filter_req.date_start:
            if "start date SAFE" in df.columns:
                df = df.filter(pl.col("start date SAFE") >= filter_req.date_start)

        if filter_req.date_end:
            if "start date SAFE" in df.columns:
                df = df.filter(pl.col("start date SAFE") <= filter_req.date_end)

        # Presence filters
        if filter_req.has_slc is True:
            if "PATH SLC" in df.columns:
                df = df.filter(pl.col("PATH SLC").is_not_null())
        elif filter_req.has_slc is False:
            if "PATH SLC" in df.columns:
                df = df.filter(pl.col("PATH SLC").is_null())

        if filter_req.has_grd is True:
            if "PATH GRD" in df.columns:
                df = df.filter(pl.col("PATH GRD").is_not_null())
        elif filter_req.has_grd is False:
            if "PATH GRD" in df.columns:
                df = df.filter(pl.col("PATH GRD").is_null())

        if filter_req.has_ocn is True:
            if "PATH OCN" in df.columns:
                df = df.filter(pl.col("PATH OCN").is_not_null())
        elif filter_req.has_ocn is False:
            if "PATH OCN" in df.columns:
                df = df.filter(pl.col("PATH OCN").is_null())

        return df
    except Exception as e:
        import logging
        import traceback

        logger = logging.getLogger(__name__)
        logger.error(f"Error in apply_filters: {e}")
        logger.error(traceback.format_exc())
        raise


import logging
import traceback

logger = logging.getLogger(__name__)


@router.post("/filter")
async def filter_catalogue(request: FilterRequest) -> dict[str, Any]:
    """Filter catalogue entries based on criteria."""
    try:
        if not catalogue_manager.is_loaded():
            raise HTTPException(status_code=503, detail="Catalogue not loaded")

        # Debug logging
        logger.info(f"Filter request: datasets={request.datasets}")
        logger.info(f"Filter request: polarization={request.polarization}")
        logger.info(f"Filter request: satellites={request.satellites}")

        df = apply_filters(catalogue_manager.df, request)

        # Select columns to return
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
    except Exception as e:
        logger.error(f"Error in filter_catalogue: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/map")
async def get_map_data(request: MapRequest) -> dict[str, Any]:
    """
    Get product data with geometry for map visualization.
    Returns polygons or centroids (points) if too many features.
    """
    if not catalogue_manager.is_loaded():
        raise HTTPException(status_code=503, detail="Catalogue not loaded")

    df = apply_filters(catalogue_manager.df, request.filter)

    # Limit polygons
    max_polygons = request.max_polygons or 100
    df = df.slice(0, max_polygons)

    features = []
    point_count = 0
    polygon_count = 0

    for row in df.to_dicts():
        # Determine which geometry column to use (prefer polygon SLC then polygon GRD)
        polygon_wkt = row.get("polygon SLC") or row.get("polygon GRD")
        if not polygon_wkt:
            continue

        try:
            geom = wkt.loads(polygon_wkt)

            # Simplify geometry for web display
            if geom.geom_type == "MultiPolygon":
                geom = shapely.ops.unary_union(geom)

            # If too many polygons, use centroids instead
            if df.height > 50:
                geom = geom.centroid
                point_count += 1
            else:
                # Simplify polygon with tolerance
                geom = geom.simplify(0.01)
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
            logger.warning(f"Error processing geometry for row: {e}")
            continue

    return {
        "type": "FeatureCollection",
        "features": features,
        "total": df.height,
        "point_count": point_count,
        "polygon_count": polygon_count,
        "is_point_mode": df.height > 50,
    }


@router.post("/heatmap/hs_tp")
async def get_hs_tp_heatmap(request: HeatmapRequest) -> dict[str, Any]:
    """Get Hs/Tp data with density estimation."""
    if not catalogue_manager.is_loaded():
        raise HTTPException(status_code=503, detail="Catalogue not loaded")

    df = apply_filters(catalogue_manager.df, request.filter)

    # Filtrer les valeurs finies (non NaN, non inf)
    hs_tp_df = df.filter(
        pl.col("Hs WW3").is_finite() & pl.col("Tp WW3").is_finite()
    )

    if hs_tp_df.height == 0:
        return {
            "data": [],
            "message": "No valid Hs/Tp data available for the selected filters",
        }

    # Extraire les tableaux numpy
    hs = hs_tp_df["Hs WW3"].to_numpy()
    tp = hs_tp_df["Tp WW3"].to_numpy()

    # Sécurité supplémentaire : supprimer les NaN
    mask = ~np.isnan(hs) & ~np.isnan(tp)
    hs = hs[mask]
    tp = tp[mask]

    if len(hs) < 2:
        return {
            "data": {"hs": hs.tolist(), "tp": tp.tolist(), "density": [1.0] * len(hs)},
            "count": len(hs),
        }

    # Calcul de la densité KDE
    data = np.vstack([hs, tp])
    kde = gaussian_kde(data)
    density = kde(data)

    # Normalisation
    density_norm = density / density.max() if density.max() > 0 else density

    return {
        "data": {
            "hs": hs.tolist(),
            "tp": tp.tolist(),
            "density": density_norm.tolist(),
        },
        "count": len(hs),
    }


@router.post("/heatmap/wind")
async def get_wind_heatmap(request: HeatmapRequest) -> dict[str, Any]:
    """Get wind direction/speed data with density estimation."""
    if not catalogue_manager.is_loaded():
        raise HTTPException(status_code=503, detail="Catalogue not loaded")

    df = apply_filters(catalogue_manager.df, request.filter)

    # Filtrer les valeurs finies pour U10 et V10
    wind_df = df.filter(
        pl.col("U10 ecmwf").is_finite() & pl.col("V10 ecmwf").is_finite()
    )

    if wind_df.height == 0:
        return {
            "data": [],
            "message": "No valid wind data available for the selected filters",
        }

    # Calcul de la vitesse et direction (identique)
    wind_df = wind_df.with_columns([
        ((pl.col("U10 ecmwf")**2 + pl.col("V10 ecmwf")**2).sqrt()).alias("wind_speed"),
        ((180 + (180 / np.pi) * pl.arctan2(pl.col("U10 ecmwf"), pl.col("V10 ecmwf"))) % 360)
        .alias("wind_direction")
    ])

    # Extraire et nettoyer
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

@router.post("/category_counts")
async def get_category_counts(request: FilterRequest) -> dict[str, Any]:
    """Get counts of products per category."""
    if not catalogue_manager.is_loaded():
        raise HTTPException(status_code=503, detail="Catalogue not loaded")

    df = apply_filters(catalogue_manager.df, request)

    if "category" not in df.columns:
        return {"counts": {}, "total": df.height}

    # Group by category
    counts_df = df.group_by("category").agg(pl.len())
    counts = dict(zip(counts_df["category"], counts_df["len"]))

    return {"counts": counts, "total": df.height}

@router.post("/daily_counts")
async def get_daily_counts(request: FilterRequest) -> dict[str, Any]:
    """Get daily product counts per dataset for stacked bar chart."""
    if not catalogue_manager.is_loaded():
        raise HTTPException(status_code=503, detail="Catalogue not loaded")

    df = apply_filters(catalogue_manager.df, request)  # <-- FIX: pass request directly

    if "start date SAFE" not in df.columns or "datasets" not in df.columns:
        return {"error": "Missing required columns"}

    # Convert to date only (ignore time)
    df = df.with_columns(pl.col("start date SAFE").dt.date().alias("date"))

    # Explode datasets and count per date+dataset
    exploded = df.explode("datasets")
    counts = exploded.group_by(["date", "datasets"]).agg(pl.len())

    # Pivot to wide format
    pivot = counts.pivot(
        index="date",
        columns="datasets",
        values="len",
        aggregate_function="sum"
    )
    pivot = pivot.fill_null(0)

    dates = pivot["date"].to_list()
    dataset_names = [c for c in pivot.columns if c != "date"]
    series = {ds: pivot[ds].to_list() for ds in dataset_names}

    # Sort dates chronologically
    sorted_indices = sorted(range(len(dates)), key=lambda i: dates[i])
    dates_sorted = [dates[i] for i in sorted_indices]
    series_sorted = {ds: [series[ds][i] for i in sorted_indices] for ds in dataset_names}

    return {
        "dates": dates_sorted,
        "series": series_sorted,
        "datasets": dataset_names,
    }

@router.post("/monthly_counts")
async def get_monthly_counts(request: FilterRequest) -> dict[str, Any]:
    """Get monthly product counts per dataset for stacked bar chart."""
    if not catalogue_manager.is_loaded():
        raise HTTPException(status_code=503, detail="Catalogue not loaded")

    df = apply_filters(catalogue_manager.df, request)

    if "start date SAFE" not in df.columns or "datasets" not in df.columns:
        return {"error": "Missing required columns"}

    # Truncate to month (first day of each month)
    df = df.with_columns(
        pl.col("start date SAFE").dt.truncate("1mo").alias("month")
    )

    # Explode datasets and count per month+dataset
    exploded = df.explode("datasets")
    counts = exploded.group_by(["month", "datasets"]).agg(pl.len())

    # Pivot to wide format
    pivot = counts.pivot(
        index="month",
        columns="datasets",
        values="len",
        aggregate_function="sum"
    )
    pivot = pivot.fill_null(0)

    months = pivot["month"].to_list()
    dataset_names = [c for c in pivot.columns if c != "month"]
    series = {ds: pivot[ds].to_list() for ds in dataset_names}

    # Sort months chronologically
    sorted_indices = sorted(range(len(months)), key=lambda i: months[i])
    months_sorted = [months[i] for i in sorted_indices]
    series_sorted = {ds: [series[ds][i] for i in sorted_indices] for ds in dataset_names}

    # Format months as strings for display (e.g., "2025-01")
    month_labels = [m.strftime("%Y-%m") for m in months_sorted]

    return {
        "months": month_labels,
        "series": series_sorted,
        "datasets": dataset_names,
    }