"""Configuration management for s1iw_catalogue."""

from pathlib import Path
from typing import Any, Dict, Optional, Union


def load_config(
    config_path: Optional[Union[str, Path]] = None,
    cli_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Load configuration from defaults, versioned file, local file, and CLI.

    Priority (higher wins): CLI overrides > localconfig.yml > config.yml > defaults.

    Args:
        config_path: Explicit path to a config file (overrides default lookup).
        cli_overrides: Dictionary of command-line overrides.

    Returns:
        Merged configuration dictionary.
    """
    ...


def get_default_config() -> Dict[str, Any]:
    """Return built-in default configuration values."""
    ...


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML file, return empty dict if not found."""
    ...


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge two dictionaries."""
    ...