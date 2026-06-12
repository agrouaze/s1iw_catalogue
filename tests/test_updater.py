"""Test CatalogueUpdater skeleton."""

from pathlib import Path

import pytest

from s1iw_catalogue.schema import create_empty_catalogue
from s1iw_catalogue.updater import CatalogueUpdater


@pytest.fixture
def dummy_config():
    """Return a dummy configuration dictionary for testing."""
    return {"sources": {"cdse": {}, "s1ifr": {}, "familyprod": {}}}


def test_init(dummy_config):
    """Test that CatalogueUpdater initializes with config."""
    updater = CatalogueUpdater(dummy_config)
    assert updater.config == dummy_config


def test_find_new_safe(dummy_config):
    """Test that find_new_safe method exists."""
    updater = CatalogueUpdater(dummy_config)
    _existing = create_empty_catalogue()
    _slc_listing = Path("/dummy/slc.csv")
    _grd_listing = Path("/dummy/grd.csv")
    assert hasattr(updater, "find_new_safe")


def test_update_presence_columns(dummy_config):
    """Test that update_presence_columns method exists."""
    updater = CatalogueUpdater(dummy_config)
    _df = create_empty_catalogue()
    assert hasattr(updater, "update_presence_columns")


def test_update_dataset_membership(dummy_config):
    """Test that update_dataset_membership method exists."""
    updater = CatalogueUpdater(dummy_config)
    _df = create_empty_catalogue()
    assert hasattr(updater, "update_dataset_membership")


def test_update_meteorology(dummy_config):
    """Test that update_meteorology method exists."""
    updater = CatalogueUpdater(dummy_config)
    _df = create_empty_catalogue()
    assert hasattr(updater, "update_meteorology")
