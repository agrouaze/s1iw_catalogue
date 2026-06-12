"""Core catalogue class for s1iw_catalogue."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import polars as pl

from s1iw_catalogue.config import load_config
from s1iw_catalogue.schema import create_empty_catalogue


class S1IWCatalogue:
    """Main class for managing the Sentinel-1 IW exhaustive catalogue."""

    def __init__(
        self,
        catalogue_path: Union[str, Path],
        config: Optional[Union[str, Path, dict]] = None,
    ) -> None:
        self._catalogue_path = Path(catalogue_path)
        self._config = load_config() if config is None else config

    def create(self, output_path: Optional[Union[str, Path]] = None) -> None:
        pass

    def update(self, force_meteo_refresh: bool = False) -> None:
        pass

    def stats(self, dataset: Optional[str] = None, verbose: bool = False, output: Optional[Union[str, Path]] = None) -> dict:
        return {}

    def backup(self, backup_dir: Optional[Union[str, Path]] = None) -> Path:
        return Path()

    def query(self, safe_name: str) -> Optional[dict]:
        return None

    def get_centroids(self) -> pl.DataFrame:
        return create_empty_catalogue()

    def _load_catalogue(self) -> pl.DataFrame:
        return create_empty_catalogue()

    def _save_catalogue(self, df: pl.DataFrame) -> None:
        pass

    def _merge_updates(self, new_rows: pl.DataFrame) -> pl.DataFrame:
        return create_empty_catalogue()