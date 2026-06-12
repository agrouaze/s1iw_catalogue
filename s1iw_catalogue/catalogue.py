"""Core catalogue class for s1iw_catalogue."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import polars as pl


class S1IWCatalogue:
    """Main class for managing the Sentinel-1 IW exhaustive catalogue."""

    def __init__(
        self,
        catalogue_path: Union[str, Path],
        config: Optional[Union[str, Path, dict]] = None,
    ) -> None:
        """Initialize catalogue instance.

        Args:
            catalogue_path: Path to the .parquet file.
            config: Path to config file or dict with configuration.
        """
        ...

    def create(self, output_path: Optional[Union[str, Path]] = None) -> None:
        """Create a brand new catalogue from scratch.

        Args:
            output_path: Where to write the new catalogue. If None, use self.catalogue_path.
        """
        ...

    def update(self, force_meteo_refresh: bool = False) -> None:
        """Incrementally update the existing catalogue.

        Args:
            force_meteo_refresh: If True, refresh meteorological columns even if already filled.
        """
        ...

    def stats(
        self,
        dataset: Optional[str] = None,
        verbose: bool = False,
        output: Optional[Union[str, Path]] = None,
    ) -> dict:
        """Compute statistics about the catalogue.

        Args:
            dataset: Filter statistics to a specific dataset (e.g., "sarwave").
            verbose: Print detailed statistics to console.
            output: Optional JSON file path to export statistics.

        Returns:
            Dictionary with statistics.
        """
        ...

    def backup(self, backup_dir: Optional[Union[str, Path]] = None) -> Path:
        """Create a timestamped backup of the current catalogue.

        Args:
            backup_dir: Directory to store backups. If None, use config value.

        Returns:
            Path to the created backup file.
        """
        ...

    def query(self, safe_name: str) -> Optional[dict]:
        """Look up a SAFE by name and return its row as a dictionary.

        Args:
            safe_name: Name of the SAFE product (SLC, GRD, or OCN).

        Returns:
            Row data as dict, or None if not found.
        """
        ...

    def get_centroids(self) -> pl.DataFrame:
        """Extract centroids from polygon column for spatial operations.

        Returns:
            DataFrame with columns: safe_name, centroid_lon, centroid_lat.
        """
        ...

    def _load_catalogue(self) -> pl.DataFrame:
        """Load the catalogue into memory (lazy or eager)."""
        ...

    def _save_catalogue(self, df: pl.DataFrame) -> None:
        """Save the catalogue atomically (temp file then rename)."""
        ...

    def _merge_updates(self, new_rows: pl.DataFrame) -> pl.DataFrame:
        """Merge new/updated rows with existing catalogue, handling deduplication."""
        ...