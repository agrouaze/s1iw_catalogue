"""
s1iw_catalogue – Exhaustive catalogue of Sentinel-1 IW SAFE products for Ifremer.
"""

from __future__ import annotations

from ._version import __version__, version, version_tuple
# ✅ Kept: stats.py is copied in Docker and needed by the web app
from .stats import CatalogueStats

# ❌ REMOVED: catalogue.py and config.py are NOT in the Docker image
# from .catalogue import S1IWCatalogue
# from .config import load_config

__all__ = [
    "__version__",
    "version",
    "version_tuple",
    # "S1IWCatalogue",
    # "load_config",
    "CatalogueStats",
]