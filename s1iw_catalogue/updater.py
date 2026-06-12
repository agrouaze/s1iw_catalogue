"""Incremental update logic for the catalogue."""

from pathlib import Path
from typing import List, Optional

import polars as pl

from s1iw_catalogue.config import S1IWCatalogueConfig  # hypothetical typed config


class CatalogueUpdater:
    """Handles incremental updates of the catalogue."""

    def __init__(self, config: dict) -> None:
        """Initialize with configuration."""
        ...

    def find_new_safe(
        self,
        existing_df: pl.DataFrame,
        slc_listing: Path,
        grd_listing: Path,
    ) -> pl.DataFrame:
        """Identify SAFE not yet present in the catalogue.

        Returns:
            DataFrame of new rows (with columns matching schema).
        """
        ...

    def update_presence_columns(
        self,
        df: pl.DataFrame,
        force: bool = False,
    ) -> pl.DataFrame:
        """Query s1ifr for each SAFE to fill presence columns.

        Args:
            df: DataFrame with existing rows (maybe missing presence paths).
            force: If True, re-query even if already filled.

        Returns:
            Updated DataFrame with presence columns filled.
        """
        ...

    def update_dataset_membership(
        self,
        df: pl.DataFrame,
    ) -> pl.DataFrame:
        """Query familyprod to add dataset(s) d'appartenance.

        Merges new datasets into existing array column.
        """
        ...

    def update_meteorology(
        self,
        df: pl.DataFrame,
        force: bool = False,
    ) -> pl.DataFrame:
        """Add ECMWF/WW3 columns (Hs, Tp, U10, V10) for rows that lack them."""
        ...

    def _get_safe_centroid(self, polygon_wkt: str) -> tuple[float, float]:
        """Extract centroid (lon, lat) from WKT polygon."""
        ...

    def _call_cdse_match(self, safe_name: str) -> List[str]:
        """Find associated GRD for a given SLC (or vice versa)."""
        ...