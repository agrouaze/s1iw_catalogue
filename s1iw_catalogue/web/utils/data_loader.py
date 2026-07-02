"""Catalogue loading and caching utilities."""

from typing import Optional

import logging
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)


class CatalogueManager:
    """Manages catalogue loading, caching, and access."""

    def __init__(self):
        self._df: pl.DataFrame | None = None
        self._path: Path | None = None

    def load(self, path: Path) -> None:
        """Load catalogue from parquet file."""
        if not path.exists():
            raise FileNotFoundError(f"Catalogue not found: {path}")

        logger.info(f"Loading catalogue: {path}")
        self._df = pl.read_parquet(path)
        self._path = path
        logger.info(f"Loaded {self._df.height} rows")

    def clear(self) -> None:
        """Clear loaded catalogue."""
        self._df = None
        self._path = None

    def is_loaded(self) -> bool:
        """Check if catalogue is loaded."""
        return self._df is not None

    @property
    def df(self) -> pl.DataFrame:
        """Get the catalogue DataFrame."""
        if self._df is None:
            raise RuntimeError("Catalogue not loaded. Call load() first.")
        return self._df

    @property
    def path(self) -> Path | None:
        """Get the catalogue file path."""
        return self._path

    def row_count(self) -> int:
        """Get number of rows in catalogue."""
        return self._df.height if self._df is not None else 0

    def refresh(self) -> None:
        """Reload catalogue from disk."""
        if self._path:
            self.load(self._path)
        else:
            logger.warning("Cannot refresh: no catalogue path set")


# Singleton instance
catalogue_manager = CatalogueManager()
