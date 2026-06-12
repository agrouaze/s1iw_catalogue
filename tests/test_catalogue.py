"""Test S1IWCatalogue class skeleton."""

from pathlib import Path
from unittest.mock import patch

import polars as pl
import pytest

from s1iw_catalogue.catalogue import S1IWCatalogue


@pytest.fixture
def dummy_catalogue_path(tmp_path):
    return tmp_path / "catalogue.parquet"


def test_init(dummy_catalogue_path):
    cat = S1IWCatalogue(dummy_catalogue_path)
    assert cat._catalogue_path == dummy_catalogue_path


def test_create_method_exists(dummy_catalogue_path):
    cat = S1IWCatalogue(dummy_catalogue_path)
    assert hasattr(cat, "create")
    # We'll test the call later when implemented


def test_update_method_exists(dummy_catalogue_path):
    cat = S1IWCatalogue(dummy_catalogue_path)
    assert hasattr(cat, "update")


def test_stats_method_exists(dummy_catalogue_path):
    cat = S1IWCatalogue(dummy_catalogue_path)
    assert hasattr(cat, "stats")


def test_backup_method_exists(dummy_catalogue_path):
    cat = S1IWCatalogue(dummy_catalogue_path)
    assert hasattr(cat, "backup")


def test_query_method_exists(dummy_catalogue_path):
    cat = S1IWCatalogue(dummy_catalogue_path)
    assert hasattr(cat, "query")


def test_get_centroids_method_exists(dummy_catalogue_path):
    cat = S1IWCatalogue(dummy_catalogue_path)
    assert hasattr(cat, "get_centroids")
