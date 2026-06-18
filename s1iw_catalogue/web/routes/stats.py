"""Statistics API routes."""

import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
import polars as pl
from s1iw_catalogue.stats import CatalogueStats
from s1iw_catalogue.web.utils.data_loader import catalogue_manager
from s1iw_catalogue.web.models import GlobalStatsResponse, DatasetCompletenessResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/global", response_model=GlobalStatsResponse)
async def get_global_stats() -> Dict[str, Any]:
    """Get global statistics about the catalogue."""
    if not catalogue_manager.is_loaded():
        raise HTTPException(status_code=503, detail="Catalogue not loaded")
    
    df = catalogue_manager.df
    stats = CatalogueStats(df)
    
    # Compute global stats
    result = {
        "total_count": stats.total_count(),
        "product_type_counts": stats.product_type_counts(),
        "product_type_percentages": stats.product_type_percentages(),
        "linked_count": stats.linked_count(),
        "unlinked_slc_count": stats.unlinked_slc_count(),
        "unlinked_grd_count": stats.unlinked_grd_count(),
        "satellite_counts": stats.satellite_counts(),
        "polarization_counts": stats.polarization_counts(),
        "dataset_counts": stats.dataset_membership_counts(),
        "latest_acquisition": stats.latest_acquisition(),
        "latest_horodating": stats.latest_horodating(),
    }
    
    # Convert datetime objects to ISO strings
    if result["latest_acquisition"][1]:
        result["latest_acquisition"] = (
            result["latest_acquisition"][0],
            result["latest_acquisition"][1].isoformat(),
        )
    if result["latest_horodating"][1]:
        result["latest_horodating"] = (
            result["latest_horodating"][0],
            result["latest_horodating"][1].isoformat(),
        )
    
    return result


@router.get("/datasets", response_model=DatasetCompletenessResponse)
async def get_dataset_completeness() -> Dict[str, Any]:
    """Get dataset completeness matrix."""
    if not catalogue_manager.is_loaded():
        raise HTTPException(status_code=503, detail="Catalogue not loaded")
    
    df = catalogue_manager.df
    
    presence_cols = [
        "presence SLC",
        "presence GRD",
        "presence OCN",
        "presence L1B XSP A21",
        "presence L1C XSP B17",
    ]
    
    # Get all datasets
    if "dataset(s) d'appartenance" not in df.columns:
        return {"datasets": {}, "overall": {}}
    
    datasets = df.select(
        pl.col("dataset(s) d'appartenance").explode().unique()
    ).to_series().to_list()
    
    results = {}
    for dataset in datasets:
        dataset_df = df.filter(
            pl.col("dataset(s) d'appartenance").list.contains(dataset)
        )
        total = dataset_df.height
        
        dataset_results = {}
        for col in presence_cols:
            if col in dataset_df.columns:
                present = dataset_df.filter(pl.col(col).is_not_null()).height
                pct = (present / total * 100) if total > 0 else 0.0
                dataset_results[col] = round(pct, 1)
        
        # Calculate overall average
        presence_values = [v for k, v in dataset_results.items() if k != "presence OCN"]
        if presence_values:
            dataset_results["overall"] = round(sum(presence_values) / len(presence_values), 1)
        else:
            dataset_results["overall"] = 0.0
        
        results[dataset] = dataset_results
    
    # Overall row
    overall_results = {}
    for col in presence_cols:
        if col in df.columns:
            total = df.height
            present = df.filter(pl.col(col).is_not_null()).height
            pct = (present / total * 100) if total > 0 else 0.0
            overall_results[col] = round(pct, 1)
    
    presence_values = [v for k, v in overall_results.items() if k != "presence OCN"]
    if presence_values:
        overall_results["overall"] = round(sum(presence_values) / len(presence_values), 1)
    else:
        overall_results["overall"] = 0.0
    
    return {
        "datasets": results,
        "overall": overall_results,
    }


@router.get("/presence")
async def get_presence_stats() -> Dict[str, float]:
    """Get overall presence percentages per column."""
    if not catalogue_manager.is_loaded():
        raise HTTPException(status_code=503, detail="Catalogue not loaded")
    
    df = catalogue_manager.df
    
    presence_cols = [
        "presence SLC",
        "presence GRD",
        "presence OCN",
        "presence L1B XSP A21",
        "presence L1C XSP B17",
    ]
    
    result = {}
    for col in presence_cols:
        if col in df.columns:
            total = df.height
            present = df.filter(pl.col(col).is_not_null()).height
            result[col] = round((present / total * 100) if total > 0 else 0.0, 1)
    
    return result