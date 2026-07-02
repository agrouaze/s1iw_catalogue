"""Pydantic models for web API request/response validation."""

from typing import Any, Dict, List, Optional

from datetime import datetime

from pydantic import BaseModel, Field


class FilterRequest(BaseModel):
    """Request model for filtering catalogue entries."""

    slc_name: str | None = Field(None, description="Partial match on SAFE SLC name")
    grd_name: str | None = Field(None, description="Partial match on SAFE GRD name")
    ocn_name: str | None = Field(None, description="Partial match on SAFE OCN name")
    datasets: list[str] | None = Field(None, description="Filter by dataset names")
    polarization: list[str] | None = Field(None, description="Filter by polarization")
    satellites: list[str] | None = Field(None, description="Filter by satellite (unit)")
    date_start: datetime | None = Field(
        None, description="Start of acquisition date range"
    )
    date_end: datetime | None = Field(None, description="End of acquisition date range")
    has_slc: bool | None = Field(None, description="Only products with SLC presence")
    has_grd: bool | None = Field(None, description="Only products with GRD presence")
    has_ocn: bool | None = Field(None, description="Only products with OCN presence")
    limit: int = Field(100, ge=1, le=1000, description="Max number of results")
    offset: int = Field(0, ge=0, description="Pagination offset")


class MapRequest(BaseModel):
    """Request model for map data."""

    filter: FilterRequest = Field(..., description="Filter criteria")
    max_polygons: int = Field(
        100, ge=1, le=500, description="Max number of polygons to return"
    )


class HeatmapRequest(BaseModel):
    """Request model for heatmap data."""

    filter: FilterRequest = Field(..., description="Filter criteria")
    variable: str = Field(..., description="Variable to plot (hs_tp or wind)")


class DatasetCompletenessResponse(BaseModel):
    """Response model for dataset completeness."""

    datasets: dict[str, dict[str, float]] = Field(
        ..., description="Dataset -> column -> percentage"
    )
    overall: dict[str, float] = Field(
        ..., description="Overall completeness per column"
    )


class GlobalStatsResponse(BaseModel):
    """Response model for global statistics."""

    total_count: int
    product_type_counts: dict[str, int]
    product_type_percentages: dict[str, float]
    linked_count: int
    unlinked_slc_count: int
    unlinked_grd_count: int
    satellite_counts: dict[str, int]
    polarization_counts: dict[str, int]
    dataset_counts: dict[str, int]
    latest_acquisition: tuple[str, str]  # (safe_name, iso_datetime)
    latest_horodating: tuple[str, str]  # (safe_name, iso_datetime)
