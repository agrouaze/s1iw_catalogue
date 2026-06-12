"""Test that all modules can be imported."""

import importlib


def test_import_catalogue():
    importlib.import_module("s1iw_catalogue.catalogue")


def test_import_cli():
    importlib.import_module("s1iw_catalogue.cli")


def test_import_config():
    importlib.import_module("s1iw_catalogue.config")


def test_import_updater():
    importlib.import_module("s1iw_catalogue.updater")


def test_import_stats():
    importlib.import_module("s1iw_catalogue.stats")


def test_import_backup():
    importlib.import_module("s1iw_catalogue.backup")


def test_import_schema():
    importlib.import_module("s1iw_catalogue.schema")


def test_import_root():
    import s1iw_catalogue  # noqa: F401