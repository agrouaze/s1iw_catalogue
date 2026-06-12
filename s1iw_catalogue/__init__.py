# s1iw_catalogue/__init__.py
"""
s1iw_catalogue – Exhaustive catalogue of Sentinel-1 IW SAFE products for Ifremer.
"""

from __future__ import annotations

from ._version import __version__, version, version_tuple
from .catalogue import S1IWCatalogue
from .config import load_config
from .stats import CatalogueStats

__all__ = [
    "__version__",
    "version",
    "version_tuple",
    "S1IWCatalogue",
    "load_config",
    "CatalogueStats",
]
