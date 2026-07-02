"""Catalogue loading and caching utilities."""

import logging
from pathlib import Path
from typing import Any

import polars as pl

logger = logging.getLogger(__name__)


class CatalogueManager:
    """Manages catalogue loading, caching, and access."""

    def __init__(self):
        self._df: pl.DataFrame | None = None
        self._path: Path | None = None
        self._dataset_metadata: dict[str, dict] | None = None

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
        self._dataset_metadata = None

    def is_loaded(self) -> bool:
        """Check if catalogue is loaded."""
        return self._df is not None

    def set_dataset_metadata(self, metadata: dict[str, dict]) -> None:
        """
        Store dataset metadata (description, category, type) from the config file.

        Args:
            metadata: Mapping of dataset_name -> {"description": str, "category": str, "type": str}
        """
        self._dataset_metadata = metadata
        logger.info(f"Stored metadata for {len(metadata)} datasets")

    def get_dataset_metadata(self) -> dict[str, dict] | None:
        """
        Get the dataset metadata.

        Returns:
            dict or None: Mapping of dataset_name -> metadata, or None if not loaded.
        """
        return self._dataset_metadata

    def has_dataset_metadata(self) -> bool:
        """Check if dataset metadata is loaded."""
        return self._dataset_metadata is not None

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