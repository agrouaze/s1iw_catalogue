"""Browse API routes for filtering and exploring catalogue content."""

import logging
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException
import polars as pl
import shapely
from shapely import wkt
from shapely.geometry import shape

from s1iw_catalogue.web.models import FilterRequest, MapRequest, HeatmapRequest
from s1iw_catalogue.web.utils.data_loader import catalogue_manager

logger = logging.getLogger(__name__)
router = APIRouter()


def apply_filters(df: pl.DataFrame, filter_req: FilterRequest) -> pl.DataFrame:
    """Apply filters to catalogue DataFrame."""
    if filter_req.slc_name:
        df = df.filter(pl.col("SAFE SLC").str.contains(filter_req.slc_name))
    
    if filter_req.grd_name:
        df = df.filter(pl.col("SAFE GRD").str.contains(filter_req.grd_name))
    
    if filter_req.ocn_name:
        df = df.filter(pl.col("SAFE OCN").str.contains(filter_req.ocn_name))
    
    if filter_req.datasets:
        # Filter rows where dataset array contains any of the selected datasets
        df = df.filter(
            pl.col("dataset(s) d'appartenance").list.overlaps(filter_req.datasets)
        )
    
    if filter_req.polarization:
        df = df.filter(pl.col("polarization").is_in(filter_req.polarization))
    
    if filter_req.satellites:
        df = df.filter(pl.col("unité").is_in(filter_req.satellites))
    
    if filter_req.date_start:
        df = df.filter(pl.col("start date SAFE") >= filter_req.date_start)
    
    if filter_req.date_end:
        df = df.filter(pl.col("start date SAFE") <= filter_req.date_end)
    
    if filter_req.has_slc is True:
        df = df.filter(pl.col("presence SLC").is_not_null())
    elif filter_req.has_slc is False:
        df = df.filter(pl.col("presence SLC").is_null())
    
    if filter_req.has_grd is True:
        df = df.filter(pl.col("presence GRD").is_not_null())
    elif filter_req.has_grd is False:
        df = df.filter(pl.col("presence GRD").is_null())
    
    if filter_req.has_ocn is True:
        df = df.filter(pl.col("presence OCN").is_not_null())
    elif filter_req.has_ocn is False:
        df = df.filter(pl.col("presence OCN").is_null())
    
    return df


@router.post("/filter")
async def filter_catalogue(request: FilterRequest) -> Dict[str, Any]:
    """Filter catalogue entries based on criteria."""
    if not catalogue_manager.is_loaded():
        raise HTTPException(status_code=503, detail="Catalogue not loaded")
    
    df = apply_filters(catalogue_manager.df, request)
    
    # Select columns to return
    columns = ["SAFE SLC", "SAFE GRD", "SAFE OCN", "dataset(s) d'appartenance",
               "start date SAFE", "horodating", "polarization", "unité"]
    columns = [c for c in columns if c in df.columns]
    
    result_df = df.select(columns).slice(request.offset, request.limit)
    
    return {
        "total": df.height,
        "limit": request.limit,
        "offset": request.offset,
        "rows": result_df.to_dicts(),
    }


@router.post("/map")
async def get_map_data(request: MapRequest) -> Dict[str, Any]:
    """Get product data with geometry for map visualization."""
    if not catalogue_manager.is_loaded():
        raise HTTPException(status_code=503, detail="Catalogue not loaded")
    
    df = apply_filters(catalogue_manager.df, request.filter)
    
    # Limit polygons
    df = df.slice(0, request.max_polygons)
    
    features = []
    for row in df.to_dicts():
        # Determine which geometry column to use
        polygon_wkt = row.get("polygon SLC") or row.get("polygon GRD")
        if not polygon_wkt:
            continue
        
        try:
            geom = wkt.loads(polygon_wkt)
            # Simplify geometry for web display
            if geom.geom_type == "MultiPolygon":
                geom = shapely.ops.unary_union(geom)
            simplified = geom.simplify(0.01)  # Tolerance in degrees
            
            feature = {
                "type": "Feature",
                "geometry": shapely.geometry.mapping(simplified),
                "properties": {
                    "safe_slc": row.get("SAFE SLC"),
                    "safe_grd": row.get("SAFE GRD"),
                    "safe_ocn": row.get("SAFE OCN"),
                    "dataset": row.get("dataset(s) d'appartenance"),
                    "polarization": row.get("polarization"),
                    "satellite": row.get("unité"),
                    "start_date": row.get("start date SAFE"),
                }
            }
            features.append(feature)
        except Exception as e:
            logger.warning(f"Error processing geometry for row: {e}")
            continue
    
    return {
        "type": "FeatureCollection",
        "features": features,
        "total": df.height,
    }


@router.post("/heatmap/hs_tp")
async def get_hs_tp_heatmap(request: HeatmapRequest) -> Dict[str, Any]:
    """Get Hs/Tp data for heatmap visualization."""
    if not catalogue_manager.is_loaded():
        raise HTTPException(status_code=503, detail="Catalogue not loaded")
    
    df = apply_filters(catalogue_manager.df, request.filter)
    
    # Filter rows with both Hs and Tp
    hs_tp_df = df.filter(
        pl.col("Hs WW3").is_not_null() & 
        pl.col("Tp WW3").is_not_null()
    )
    
    if hs_tp_df.height == 0:
        return {"data": [], "message": "No Hs/Tp data available for the selected filters"}
    
    # Extract data
    data = {
        "hs": hs_tp_df["Hs WW3"].to_list(),
        "tp": hs_tp_df["Tp WW3"].to_list(),
    }
    
    return {"data": data, "count": hs_tp_df.height}


@router.post("/heatmap/wind")
async def get_wind_heatmap(request: HeatmapRequest) -> Dict[str, Any]:
    """Get wind direction/speed data for heatmap visualization."""
    if not catalogue_manager.is_loaded():
        raise HTTPException(status_code=503, detail="Catalogue not loaded")
    
    df = apply_filters(catalogue_manager.df, request.filter)
    
    # Filter rows with both U10 and V10
    wind_df = df.filter(
        pl.col("U10 ecmwf").is_not_null() & 
        pl.col("v10 ecmwf").is_not_null()
    )
    
    if wind_df.height == 0:
        return {"data": [], "message": "No wind data available for the selected filters"}
    
    # Extract data
    data = {
        "u10": wind_df["U10 ecmwf"].to_list(),
        "v10": wind_df["v10 ecmwf"].to_list(),
    }
    
    return {"data": data, "count": wind_df.height}