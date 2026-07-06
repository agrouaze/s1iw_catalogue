"""Test S1IWCatalogue class skeleton."""

import pytest

from s1iw_catalogue.catalogue import S1IWCatalogue


@pytest.fixture
def temp_catalogue_path(tmp_path):
    """Return a temporary catalogue file path."""
    return tmp_path / "catalogue.parquet"


def test_init(temp_catalogue_path):
    """Test that S1IWCatalogue initializes correctly."""
    cat = S1IWCatalogue(temp_catalogue_path)
    assert (
        cat._catalogue_path == temp_catalogue_path
    )  # pylint: disable=protected-access


def test_create_method_exists(temp_catalogue_path):
    """Test that create method exists."""
    cat = S1IWCatalogue(temp_catalogue_path)
    assert hasattr(cat, "create")


def test_update_method_exists(temp_catalogue_path):
    """Test that update method exists."""
    cat = S1IWCatalogue(temp_catalogue_path)
    assert hasattr(cat, "update")


def test_stats_method_exists(temp_catalogue_path):
    """Test that stats method exists."""
    cat = S1IWCatalogue(temp_catalogue_path)
    assert hasattr(cat, "stats")


def test_backup_method_exists(temp_catalogue_path):
    """Test that backup method exists."""
    cat = S1IWCatalogue(temp_catalogue_path)
    assert hasattr(cat, "backup")


def test_query_method_exists(temp_catalogue_path):
    """Test that query method exists."""
    cat = S1IWCatalogue(temp_catalogue_path)
    assert hasattr(cat, "query")


def test_get_centroids_method_exists(temp_catalogue_path):
    """Test that get_centroids method exists."""
    cat = S1IWCatalogue(temp_catalogue_path)
    assert hasattr(cat, "get_centroids")
