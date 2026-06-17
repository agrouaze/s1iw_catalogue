"""Configuration management for s1iw_catalogue."""

from typing import Any, Dict, Optional, Union

from pathlib import Path

import yaml


def get_default_config() -> dict[str, Any]:
    """Return built-in default configuration values."""
    return {
        "paths": {
            "reference_listings": {
                "slc": "/shared/listings/slc_reference.csv",
                "grd": "/shared/listings/grd_reference.csv",
                "coloc": "/shared/listings/colocalisation_listings.csv",
            },
            "output": {
                "catalogue": "/shared/catalogues/sentinel-1_exhaustive_IW_SAFE_working_material.parquet",
                "backups": "/shared/catalogues/backups/",
            },
        },
        "sources": {
            "cdse": {
                "api_url": "https://dataspace.copernicus.eu",
                "timeout_seconds": 300,
                "max_retries": 3,
            },
            "s1ifr": {"endpoint": "https://ifremer-s1ifr.internal/api"},
            "familyprod": {"database_path": "/shared/familyprod/products.db"},
        },
        "enrichment": {
            "ecmwf": {"enabled": True, "grid_resolution": 0.1},
            "ww3": {"enabled": False},
        },
        "update_rules": {"force_meteo_refresh": False, "incremental_only": True},
        "backup": {"keep_last": 7, "compression": "snappy"},
        "logging": {"level": "INFO", "file": "/var/log/s1iw_catalogue.log"},
    }


def load_config(
    config_path: str | Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load configuration from defaults, versioned file, local file, and CLI."""
    cfg = get_default_config()

    # Try to load versioned config.yml
    versioned_path = Path("config.yml") if config_path is None else Path(config_path)
    if versioned_path.exists():
        cfg = _deep_merge(cfg, _load_yaml(versioned_path))

    # Override with localconfig.yml (if exists)
    local_path = Path("localconfig.yml")
    if local_path.exists():
        cfg = _deep_merge(cfg, _load_yaml(local_path))

    # Override with CLI arguments
    if cli_overrides:
        cfg = _deep_merge(cfg, cli_overrides)

    return cfg


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load YAML file, return empty dict if not found."""
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class S1IWCatalogueConfig(dict[str, Any]):
    """Typed configuration dictionary (placeholder)."""

    pass
