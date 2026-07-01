"""Pydantic models for web API request/response validation."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class FilterRequest(BaseModel):
    """Request model for filtering catalogue entries."""
    
    slc_name: Optional[str] = Field(None, description="Partial match on SAFE SLC name")
    grd_name: Optional[str] = Field(None, description="Partial match on SAFE GRD name")
    ocn_name: Optional[str] = Field(None, description="Partial match on SAFE OCN name")
    datasets: Optional[List[str]] = Field(None, description="Filter by dataset names")
    polarization: Optional[List[str]] = Field(None, description="Filter by polarization")
    satellites: Optional[List[str]] = Field(None, description="Filter by satellite (unit)")
    date_start: Optional[datetime] = Field(None, description="Start of acquisition date range")
    date_end: Optional[datetime] = Field(None, description="End of acquisition date range")
    has_slc: Optional[bool] = Field(None, description="Only products with SLC presence")
    has_grd: Optional[bool] = Field(None, description="Only products with GRD presence")
    has_ocn: Optional[bool] = Field(None, description="Only products with OCN presence")
    limit: int = Field(100, ge=1, le=1000, description="Max number of results")
    offset: int = Field(0, ge=0, description="Pagination offset")


class MapRequest(BaseModel):
    """Request model for map data."""
    
    filter: FilterRequest = Field(..., description="Filter criteria")
    max_polygons: int = Field(100, ge=1, le=500, description="Max number of polygons to return")

class HeatmapRequest(BaseModel):
    """Request model for heatmap data."""
    
    filter: FilterRequest = Field(..., description="Filter criteria")
    variable: str = Field(..., description="Variable to plot (hs_tp or wind)")


class DatasetCompletenessResponse(BaseModel):
    """Response model for dataset completeness."""
    
    datasets: Dict[str, Dict[str, float]] = Field(..., description="Dataset -> column -> percentage")
    overall: Dict[str, float] = Field(..., description="Overall completeness per column")


class GlobalStatsResponse(BaseModel):
    """Response model for global statistics."""
    
    total_count: int
    product_type_counts: Dict[str, int]
    product_type_percentages: Dict[str, float]
    linked_count: int
    unlinked_slc_count: int
    unlinked_grd_count: int
    satellite_counts: Dict[str, int]
    polarization_counts: Dict[str, int]
    dataset_counts: Dict[str, int]
    latest_acquisition: tuple[str, str]  # (safe_name, iso_datetime)
    latest_horodating: tuple[str, str]   # (safe_name, iso_datetime)