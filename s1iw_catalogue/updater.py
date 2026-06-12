"""Incremental update logic for the catalogue."""

from typing import List, Optional

from pathlib import Path

import polars as pl


class CatalogueUpdater:
    """Handles incremental updates of the catalogue."""

    def __init__(self, config: dict) -> None:
        self.config = config

    def find_new_safe(
        self,
        existing_df: pl.DataFrame,
        slc_listing: Path,
        grd_listing: Path,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def update_presence_columns(
        self,
        df: pl.DataFrame,
        force: bool = False,
    ) -> pl.DataFrame:
        return df

    def update_dataset_membership(
        self,
        df: pl.DataFrame,
    ) -> pl.DataFrame:
        return df

    def update_meteorology(
        self,
        df: pl.DataFrame,
        force: bool = False,
    ) -> pl.DataFrame:
        return df

    def _get_safe_centroid(self, polygon_wkt: str) -> tuple[float, float]:
        return (0.0, 0.0)

    def _call_cdse_match(self, safe_name: str) -> list[str]:
        return []
