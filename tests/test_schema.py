"""Test schema definition and validation."""

import polars as pl
import pytest

from s1iw_catalogue import schema


def test_schema_dict_has_all_columns():
    """SCHEMA should contain exactly the expected columns."""
    expected_columns = [
        "SAFE SLC",
        "SAFE GRD",
        "SAFE OCN",
        "presence SLC",
        "presence GRD",
        "presence OCN",
        "presence L1B XSP A21",
        "presence L1C XSP B17",
        "dataset(s) d'appartenance",
        "Hs WW3",
        "Tp WW3",
        "U10 ecmwf",
        "v10 ecmwf",
        "start date SAFE",
        "horodating",
        "polygon of the acquisition from CDSE",
        "S3path from CDSE",
        "polarization",
        "unité",
    ]
    assert set(schema.SCHEMA.keys()) == set(expected_columns)


def test_create_empty_catalogue():
    df = schema.create_empty_catalogue()
    assert isinstance(df, pl.DataFrame)
    assert df.shape == (0, len(schema.SCHEMA))
    # Check dtypes match SCHEMA
    for col, dtype in schema.SCHEMA.items():
        assert df[col].dtype == dtype


def test_validate_schema_with_valid_df():
    df = schema.create_empty_catalogue()
    assert schema.validate_schema(df) is True


def test_validate_schema_with_invalid_df():
    df = pl.DataFrame({"wrong": [1, 2]})
    assert schema.validate_schema(df) is False