"""Parquet schema definition for the catalogue."""

from typing import Any, Dict

import polars as pl
from polars.datatypes import DataType

SCHEMA: dict[str, Any] = {
    "SAFE SLC": pl.Utf8,
    "SAFE GRD": pl.Utf8,
    "SAFE OCN": pl.Utf8,
    "presence SLC": pl.Utf8,
    "presence GRD": pl.Utf8,
    "presence OCN": pl.Utf8,
    "presence L1B XSP A21": pl.Utf8,
    "presence L1C XSP B17": pl.Utf8,
    "dataset(s) d'appartenance": pl.List(pl.Utf8),
    "Hs WW3": pl.Float32,
    "Tp WW3": pl.Float32,
    "U10 ecmwf": pl.Float32,
    "v10 ecmwf": pl.Float32,
    "start date SAFE": pl.Datetime,
    "horodating": pl.Datetime,
    "polygon SLC": pl.Utf8,  # <-- changed
    "polygon GRD": pl.Utf8,  # <-- changed
    "S3path SLC": pl.Utf8,  # <-- changed
    "S3path GRD": pl.Utf8,  # <-- changed
    "polarization": pl.Utf8,
    "unité": pl.Utf8,
}


def validate_schema(df: pl.DataFrame) -> bool:
    """Check that DataFrame has all required columns with correct types."""
    if df is None:
        return False
    for col, dtype in SCHEMA.items():
        if col not in df.columns:
            return False
        if df[col].dtype != dtype:
            # For list columns, polars uses pl.List, but sometimes the inner type may differ
            # We'll be lenient for now
            if isinstance(dtype, pl.List) and isinstance(df[col].dtype, pl.List):
                continue
            return False
    return True


def create_empty_catalogue() -> pl.DataFrame:
    """Return an empty DataFrame with the correct schema."""
    return pl.DataFrame(schema=SCHEMA)
