"""Test CatalogueUpdater skeleton."""

from pathlib import Path

import polars as pl
import pytest

from s1iw_catalogue.updater import CatalogueUpdater
from s1iw_catalogue.schema import create_empty_catalogue


@pytest.fixture
def dummy_config():
    return {"sources": {"cdse": {}, "s1ifr": {}, "familyprod": {}}}


def test_init(dummy_config):
    updater = CatalogueUpdater(dummy_config)
    assert updater.config == dummy_config


def test_find_new_safe(dummy_config):
    updater = CatalogueUpdater(dummy_config)
    existing = create_empty_catalogue()
    slc_listing = Path("/dummy/slc.csv")
    grd_listing = Path("/dummy/grd.csv")
    # Since not implemented, just test method exists
    assert hasattr(updater, "find_new_safe")
    # We'll later mock


def test_update_presence_columns(dummy_config):
    updater = CatalogueUpdater(dummy_config)
    df = create_empty_catalogue()
    assert hasattr(updater, "update_presence_columns")


def test_update_dataset_membership(dummy_config):
    updater = CatalogueUpdater(dummy_config)
    df = create_empty_catalogue()
    assert hasattr(updater, "update_dataset_membership")


def test_update_meteorology(dummy_config):
    updater = CatalogueUpdater(dummy_config)
    df = create_empty_catalogue()
    assert hasattr(updater, "update_meteorology")