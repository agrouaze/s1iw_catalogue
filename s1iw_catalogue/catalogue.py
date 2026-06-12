"""Core catalogue class for s1iw_catalogue."""

from __future__ import annotations

from typing import Optional, Union

from pathlib import Path

import polars as pl

from s1iw_catalogue.config import load_config
from s1iw_catalogue.schema import create_empty_catalogue


class S1IWCatalogue:
    """Main class for managing the Sentinel-1 IW exhaustive catalogue."""

    def __init__(
        self,
        catalogue_path: str | Path,
        config: str | Path | dict | None = None,
    ) -> None:
        self._catalogue_path = Path(catalogue_path)
        self._config = load_config() if config is None else config

    def create(self, output_path: str | Path | None = None) -> None:
        pass

    def update(self, force_meteo_refresh: bool = False) -> None:
        pass

    def stats(
        self,
        dataset: str | None = None,
        verbose: bool = False,
        output: str | Path | None = None,
    ) -> dict:
        return {}

    def backup(self, backup_dir: str | Path | None = None) -> Path:
        return Path()

    def query(self, safe_name: str) -> dict | None:
        return None

    def get_centroids(self) -> pl.DataFrame:
        return create_empty_catalogue()

    def _load_catalogue(self) -> pl.DataFrame:
        return create_empty_catalogue()

    def _save_catalogue(self, df: pl.DataFrame) -> None:
        pass

    def _merge_updates(self, new_rows: pl.DataFrame) -> pl.DataFrame:
        return create_empty_catalogue()
