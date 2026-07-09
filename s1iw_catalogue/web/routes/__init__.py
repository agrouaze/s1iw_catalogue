"""API routes for the web interface."""

from s1iw_catalogue.web.routes import browse, stats
from s1iw_catalogue.web.routes.responses import (
    COUNTS_RESPONSES,
    EXPORT_RESPONSES,
    FILTER_RESPONSES,
    HEATMAP_RESPONSES,
    MAP_RESPONSES,
    METADATA_RESPONSES,
    MONTHLY_TIMESERIES_RESPONSES,
    TIMESERIES_RESPONSES,
    WIND_HEATMAP_RESPONSES,
)

__all__ = [
    "stats",
    "browse",
    "FILTER_RESPONSES",
    "EXPORT_RESPONSES",
    "MAP_RESPONSES",
    "HEATMAP_RESPONSES",
    "WIND_HEATMAP_RESPONSES",
    "COUNTS_RESPONSES",
    "TIMESERIES_RESPONSES",
    "MONTHLY_TIMESERIES_RESPONSES",
    "METADATA_RESPONSES",
]
