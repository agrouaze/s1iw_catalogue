"""Test configuration loading and merging."""

from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from s1iw_catalogue import config


def test_get_default_config_returns_dict():
    defaults = config.get_default_config()
    assert isinstance(defaults, dict)
    # At least some expected keys
    assert "paths" in defaults
    assert "sources" in defaults


def test_load_config_no_files(tmp_path):
    """With no config files, should return defaults."""
    with patch("pathlib.Path.exists", return_value=False):
        cfg = config.load_config()
        assert cfg == config.get_default_config()


def test_load_config_with_versioned_file(tmp_path):
    """Versioned config.yml should override defaults."""
    versioned_content = """
paths:
  output:
    catalogue: "/custom/catalogue.parquet"
"""
    versioned_path = tmp_path / "config.yml"
    versioned_path.write_text(versioned_content)

    with patch("s1iw_catalogue.config._load_yaml") as mock_load:
        # Simulate loading: first call returns versioned, second local not exist
        def fake_load(path):
            if path == versioned_path:
                return {"paths": {"output": {"catalogue": "/custom/catalogue.parquet"}}}
            return {}
        mock_load.side_effect = fake_load

        cfg = config.load_config(config_path=versioned_path)
        assert cfg["paths"]["output"]["catalogue"] == "/custom/catalogue.parquet"


def test_load_config_with_local_override(tmp_path):
    """localconfig.yml should override versioned."""
    versioned = tmp_path / "config.yml"
    versioned.write_text("paths:\n  output:\n    catalogue: /versioned.parquet")
    local = tmp_path / "localconfig.yml"
    local.write_text("paths:\n  output:\n    catalogue: /local.parquet")

    with patch("s1iw_catalogue.config._load_yaml") as mock_load:
        def fake_load(path):
            if path == versioned:
                return {"paths": {"output": {"catalogue": "/versioned.parquet"}}}
            if path == local:
                return {"paths": {"output": {"catalogue": "/local.parquet"}}}
            return {}
        mock_load.side_effect = fake_load

        cfg = config.load_config(config_path=versioned)
        assert cfg["paths"]["output"]["catalogue"] == "/local.parquet"


def test_load_config_with_cli_overrides():
    cli = {"paths": {"output": {"catalogue": "/cli.parquet"}}}
    with patch("s1iw_catalogue.config._load_yaml", return_value={}):
        cfg = config.load_config(cli_overrides=cli)
        assert cfg["paths"]["output"]["catalogue"] == "/cli.parquet"