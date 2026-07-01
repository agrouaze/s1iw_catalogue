"""Parquet schema definition for the catalogue."""

from typing import Any, Dict

import polars as pl
import numpy as np

# Full schema with all columns
SCHEMA: dict[str, Any] = {
    # SAFE product identifiers
    "SAFE SLC": pl.Utf8,
    "SAFE GRD": pl.Utf8,
    "SAFE OCN": pl.Utf8,
    
    # Paths
    "PATH SLC": pl.Utf8,
    "PATH GRD": pl.Utf8,
    "PATH OCN": pl.Utf8,
    "PATH L1B XSP A21": pl.Utf8,
    "PATH L1C XSP B17": pl.Utf8,
    
    # Datasets and metadata
    "datasets": pl.List(pl.Utf8),
    "category": pl.Utf8,
    
    # WW3 wave variables (single values from nearest grid point)
    "Hs WW3": pl.Float32,      # Significant wave height at nearest WW3 grid point
    "Tp WW3": pl.Float32,      # Peak period at nearest WW3 grid point
    
    # ECMWF variables
    "U10 ecmwf": pl.Float32,
    "v10 ecmwf": pl.Float32,
    
    # Time columns
    "start date SAFE": pl.Datetime,
    "horodating": pl.Datetime,
    
    # Geometry and paths
    "polygon SLC": pl.Utf8,
    "polygon GRD": pl.Utf8,
    "S3path SLC": pl.Utf8,
    "S3path GRD": pl.Utf8,
    
    # Product metadata
    "polarization": pl.Utf8,
    "unit": pl.Utf8,
}

# List of WW3 column names for easy reference
WW3_COLUMNS = ["Hs WW3", "Tp WW3"]

# List of all expected columns
ALL_COLUMNS = list(SCHEMA.keys())


def validate_schema(df: pl.DataFrame) -> bool:
    """
    Check that DataFrame has all required columns with correct types.
    
    Args:
        df: Polars DataFrame to validate
    
    Returns:
        bool: True if schema is valid
    """
    if df is None:
        return False
    
    for col, dtype in SCHEMA.items():
        if col not in df.columns:
            print(f"Missing column: {col}")
            return False
        
        # Check dtype
        if df[col].dtype != dtype:
            # For list columns, polars uses pl.List, but sometimes the inner type may differ
            if not (isinstance(dtype, pl.List) and isinstance(df[col].dtype, pl.List)):
                print(f"Column {col} has type {df[col].dtype}, expected {dtype}")
                return False
    
    return True


def create_empty_catalogue() -> pl.DataFrame:
    """
    Return an empty DataFrame with the correct schema.
    
    Returns:
        Empty Polars DataFrame with proper schema
    """
    return pl.DataFrame(schema=SCHEMA)


def ensure_ww3_columns(df: pl.DataFrame, fill_value: float = np.nan) -> pl.DataFrame:
    """
    Ensure the DataFrame has all WW3 columns.
    Missing columns are added with fill_value.
    
    Args:
        df: Polars DataFrame
        fill_value: Value to fill missing columns with
    
    Returns:
        DataFrame with WW3 columns guaranteed
    """
    result_df = df.clone()
    for col in WW3_COLUMNS:
        if col not in result_df.columns:
            # Add empty column with correct type
            result_df = result_df.with_columns(
                pl.Series(col, [fill_value] * len(result_df)).cast(pl.Float32)
            )
    return result_df