"""Test configuration loading and merging."""

from pathlib import Path

import pytest
import yaml

from s1iw_catalogue import config


def test_get_default_config_returns_dict():
    defaults = config.get_default_config()
    assert isinstance(defaults, dict)
    assert "paths" in defaults
    assert "sources" in defaults


def test_load_config_no_files(tmp_path):
    """With no config files, should return defaults."""
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(tmp_path)  # empty directory
        cfg = config.load_config()
        assert cfg == config.get_default_config()


def test_load_config_with_versioned_file(tmp_path):
    """Versioned config.yml should override defaults."""
    versioned_content = {
        "paths": {"output": {"catalogue": "/custom/catalogue.parquet"}}
    }
    versioned_path = tmp_path / "config.yml"
    versioned_path.write_text(yaml.dump(versioned_content))

    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(tmp_path)
        cfg = config.load_config()
        assert cfg["paths"]["output"]["catalogue"] == "/custom/catalogue.parquet"


def test_load_config_with_local_override(tmp_path):
    """localconfig.yml should override versioned."""
    versioned = tmp_path / "config.yml"
    versioned.write_text(
        yaml.dump({"paths": {"output": {"catalogue": "/versioned.parquet"}}})
    )
    local = tmp_path / "localconfig.yml"
    local.write_text(yaml.dump({"paths": {"output": {"catalogue": "/local.parquet"}}}))

    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(tmp_path)
        cfg = config.load_config()
        assert cfg["paths"]["output"]["catalogue"] == "/local.parquet"


def test_load_config_with_cli_overrides(tmp_path):
    """CLI overrides should have highest priority."""
    versioned = tmp_path / "config.yml"
    versioned.write_text(
        yaml.dump({"paths": {"output": {"catalogue": "/versioned.parquet"}}})
    )
    cli = {"paths": {"output": {"catalogue": "/cli.parquet"}}}

    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(tmp_path)
        cfg = config.load_config(cli_overrides=cli)
        assert cfg["paths"]["output"]["catalogue"] == "/cli.parquet"
