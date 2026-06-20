"""Browse API routes for filtering and exploring catalogue content."""

import json
import logging
import traceback
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
import polars as pl
import shapely
from shapely import wkt
from shapely.geometry import shape, Point, mapping

from s1iw_catalogue.web.models import FilterRequest, MapRequest, HeatmapRequest
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
            if "dataset(s) d'appartenance" in df.columns:
                # Use list.contains with any() to check overlap
                # Create a condition: for any dataset in the list, check if it's in the array
                # Polars: list.contains(element) returns a boolean expression
                # We need to check if ANY of the selected datasets are in the list
                condition = pl.lit(False)
                for dataset in filter_req.datasets:
                    condition = condition | pl.col("dataset(s) d'appartenance").list.contains(dataset)
                df = df.filter(condition)
        
        # Polarization filter
        if filter_req.polarization and len(filter_req.polarization) > 0:
            if "polarization" in df.columns:
                df = df.filter(pl.col("polarization").is_in(filter_req.polarization))
        
        # Satellite filter
        if filter_req.satellites and len(filter_req.satellites) > 0:
            if "unité" in df.columns:
                df = df.filter(pl.col("unité").is_in(filter_req.satellites))
        
        # Date range filters
        if filter_req.date_start:
            if "start date SAFE" in df.columns:
                df = df.filter(pl.col("start date SAFE") >= filter_req.date_start)
        
        if filter_req.date_end:
            if "start date SAFE" in df.columns:
                df = df.filter(pl.col("start date SAFE") <= filter_req.date_end)
        
        # Presence filters
        if filter_req.has_slc is True:
            if "presence SLC" in df.columns:
                df = df.filter(pl.col("presence SLC").is_not_null())
        elif filter_req.has_slc is False:
            if "presence SLC" in df.columns:
                df = df.filter(pl.col("presence SLC").is_null())
        
        if filter_req.has_grd is True:
            if "presence GRD" in df.columns:
                df = df.filter(pl.col("presence GRD").is_not_null())
        elif filter_req.has_grd is False:
            if "presence GRD" in df.columns:
                df = df.filter(pl.col("presence GRD").is_null())
        
        if filter_req.has_ocn is True:
            if "presence OCN" in df.columns:
                df = df.filter(pl.col("presence OCN").is_not_null())
        elif filter_req.has_ocn is False:
            if "presence OCN" in df.columns:
                df = df.filter(pl.col("presence OCN").is_null())
        
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
async def filter_catalogue(request: FilterRequest) -> Dict[str, Any]:
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
    except Exception as e:
        logger.error(f"Error in filter_catalogue: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))





@router.post("/map")
async def get_map_data(request: MapRequest) -> Dict[str, Any]:
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
                    "dataset": row.get("dataset(s) d'appartenance"),
                    "polarization": row.get("polarization"),
                    "satellite": row.get("unité"),
                    "start_date": str(row.get("start date SAFE")) if row.get("start date SAFE") else None,
                    "horodating": str(row.get("horodating")) if row.get("horodating") else None,
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
        "point_count": point_count,
        "polygon_count": polygon_count,
        "is_point_mode": df.height > 50,
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