"""Shared response definitions for API documentation."""

from fastapi import status

# ============================================================================
# Common Responses
# ============================================================================
APPLICATION_JSON = "application/json"
COMMON_RESPONSES = {
    500: {
        "description": "Internal server error",
        "content": {
            APPLICATION_JSON: {"example": {"detail": "An unexpected error occurred"}}
        },
    },
    503: {
        "description": "Service unavailable - catalogue not loaded",
        "content": {APPLICATION_JSON: {"example": {"detail": "Catalogue not loaded"}}},
    },
}

# ============================================================================
# Filter Endpoint Responses
# ============================================================================

FILTER_RESPONSES = {
    200: {
        "description": "Successful response with filtered catalogue entries",
        "content": {
            APPLICATION_JSON: {
                "example": {
                    "total": 100,
                    "limit": 10,
                    "offset": 0,
                    "rows": [
                        {
                            "SAFE SLC": "S1A_IW_SLC__1SDV_20240101T120000_20240101T120012_045678_012345_6789",
                            "SAFE GRD": "S1A_IW_GRD__1SDV_20240101T120000_20240101T120012_045678_012345_6789",
                            "SAFE OCN": "S1A_IW_OCN__2SDV_20240101T120000_20240101T120012_045678_012345_6789",
                            "datasets": ["SLC", "GRD"],
                            "start date SAFE": "2024-01-01",
                            "horodating": "2024-01-01T12:00:00",
                            "polarization": "VV",
                            "unit": "S1A",
                        }
                    ],
                }
            }
        },
    },
    **COMMON_RESPONSES,
}

# ============================================================================
# Export Endpoint Responses
# ============================================================================

EXPORT_RESPONSES = {
    200: {
        "description": "CSV file successfully generated",
        "content": {
            "text/csv": {
                "example": (
                    "SAFE SLC,SAFE GRD,start date SAFE\n"
                    "S1A_IW_SLC__1SDV_20240101T...,S1A_IW_GRD__1SDV_20240101T...,2024-01-01\n"
                    "S1A_IW_SLC__1SDV_20240102T...,S1A_IW_GRD__1SDV_20240102T...,2024-01-02"
                )
            }
        },
    },
    400: {
        "description": "Invalid request parameters",
        "content": {
            APPLICATION_JSON: {
                "example": {"detail": "No valid columns selected for export"}
            }
        },
    },
    404: {
        "description": "No data found for the selected filters",
        "content": {
            APPLICATION_JSON: {
                "example": {"detail": "No data found for the selected filters"}
            }
        },
    },
    413: {
        "description": "Request too large - export would exceed maximum row limit",
        "content": {
            APPLICATION_JSON: {
                "example": {
                    "detail": "Too many rows (15000). Please refine your filters. Maximum allowed: 10000"
                }
            }
        },
    },
    **COMMON_RESPONSES,
}

# ============================================================================
# Map Endpoint Responses
# ============================================================================

MAP_RESPONSES = {
    200: {
        "description": "GeoJSON features successfully generated",
        "content": {
            APPLICATION_JSON: {
                "example": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [
                                    [
                                        [0.0, 0.0],
                                        [1.0, 0.0],
                                        [1.0, 1.0],
                                        [0.0, 1.0],
                                        [0.0, 0.0],
                                    ]
                                ],
                            },
                            "properties": {
                                "safe_slc": "S1A_IW_SLC__1SDV_20240101T...",
                                "safe_grd": "S1A_IW_GRD__1SDV_20240101T...",
                                "safe_ocn": "S1A_IW_OCN__2SDV_20240101T...",
                                "dataset": ["SLC", "GRD"],
                                "polarization": "VV",
                                "satellite": "S1A",
                                "start_date": "2024-01-01",
                                "horodating": "2024-01-01T12:00:00",
                            },
                        }
                    ],
                    "total": 100,
                    "polygon_count": 50,
                    "is_point_mode": False,
                }
            }
        },
    },
    **COMMON_RESPONSES,
}

# ============================================================================
# Heatmap Endpoint Responses
# ============================================================================

HEATMAP_RESPONSES = {
    200: {
        "description": "Heatmap data successfully generated",
        "content": {
            APPLICATION_JSON: {
                "example": {
                    "data": {
                        "hs": [1.2, 1.5, 0.8, 2.1, 1.8],
                        "tp": [8.0, 9.5, 7.0, 10.2, 8.5],
                        "density": [0.8, 1.0, 0.5, 0.9, 0.7],
                    },
                    "count": 5,
                }
            }
        },
    },
    **COMMON_RESPONSES,
}

WIND_HEATMAP_RESPONSES = {
    200: {
        "description": "Wind heatmap data successfully generated",
        "content": {
            APPLICATION_JSON: {
                "example": {
                    "data": {
                        "speed": [5.2, 6.8, 4.5, 7.1, 5.9],
                        "direction": [45.0, 120.5, 270.0, 180.0, 90.0],
                        "density": [0.7, 1.0, 0.4, 0.8, 0.6],
                    },
                    "count": 5,
                }
            }
        },
    },
    **COMMON_RESPONSES,
}

# ============================================================================
# Counts Endpoint Responses
# ============================================================================

COUNTS_RESPONSES = {
    200: {
        "description": "Category counts successfully retrieved",
        "content": {
            APPLICATION_JSON: {
                "example": {"counts": {"SLC": 50, "GRD": 30, "OCN": 20}, "total": 100}
            }
        },
    },
    **COMMON_RESPONSES,
}

# ============================================================================
# Time Series Endpoint Responses
# ============================================================================

TIMESERIES_RESPONSES = {
    200: {
        "description": "Time series data successfully retrieved",
        "content": {
            APPLICATION_JSON: {
                "example": {
                    "dates": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
                    "series": {
                        "SLC": [10, 15, 12, 18],
                        "GRD": [5, 8, 6, 10],
                        "OCN": [2, 3, 4, 5],
                    },
                    "datasets": ["SLC", "GRD", "OCN"],
                }
            }
        },
    },
    **COMMON_RESPONSES,
}

MONTHLY_TIMESERIES_RESPONSES = {
    200: {
        "description": "Monthly time series data successfully retrieved",
        "content": {
            APPLICATION_JSON: {
                "example": {
                    "months": ["2024-01", "2024-02", "2024-03", "2024-04"],
                    "series": {
                        "SLC": [30, 45, 36, 54],
                        "GRD": [15, 24, 18, 30],
                        "OCN": [6, 9, 12, 15],
                    },
                    "datasets": ["SLC", "GRD", "OCN"],
                }
            }
        },
    },
    **COMMON_RESPONSES,
}

# ============================================================================
# Metadata Endpoint Responses
# ============================================================================

METADATA_RESPONSES = {
    200: {
        "description": "Dataset metadata successfully retrieved",
        "content": {
            APPLICATION_JSON: {
                "example": {
                    "metadata": {
                        "SLC": {
                            "description": "Sentinel-1 Single Look Complex products",
                            "category": "SAR",
                            "type": "SLC",
                            "count": 50,
                        },
                        "GRD": {
                            "description": "Sentinel-1 Ground Range Detected products",
                            "category": "SAR",
                            "type": "GRD",
                            "count": 30,
                        },
                        "OCN": {
                            "description": "Sentinel-1 Ocean products",
                            "category": "OCEAN",
                            "type": "OCN",
                            "count": 20,
                        },
                    },
                    "debug": {
                        "has_datasets_col": True,
                        "dtype": "List(Utf8)",
                        "sample": [["SLC", "GRD"], ["OCN"]],
                        "non_empty_rows": 100,
                        "metadata_keys": ["SLC", "GRD", "OCN"],
                    },
                }
            }
        },
    },
    **COMMON_RESPONSES,
}
