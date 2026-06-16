"""Core catalogue class for s1iw_catalogue."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import polars as pl

from s1iw_catalogue.config import load_config
from s1iw_catalogue.schema import create_empty_catalogue
from s1iw_catalogue.updater import CatalogueUpdater


class S1IWCatalogue:
    """Main class for managing the Sentinel-1 IW exhaustive catalogue."""

    def __init__(
        self,
        catalogue_path: Union[str, Path],
        config: Optional[Union[str, Path, dict]] = None,
    ) -> None:
        self._catalogue_path = Path(catalogue_path)
        self._config = load_config() if config is None else config
        self._updater = CatalogueUpdater(self._config)

    def create(self, output_path: Optional[Union[str, Path]] = None) -> None:
        """Create a brand new catalogue from scratch."""
        out_path = Path(output_path) if output_path else self._catalogue_path
        # Get listing configurations (can be string, list, or directory)
        slc_listings = self._config["paths"]["reference_listings"]["slc"]
        grd_listings = self._config["paths"]["reference_listings"]["grd"]
        # Build catalogue from listings
        df = self._updater.build_from_listings(slc_listings, grd_listings)
        # Write to Parquet
        df.write_parquet(out_path, compression="snappy")
        print(f"Catalogue created at {out_path}")

    def update(self, force_meteo_refresh: bool = False) -> None:
        """Incrementally update the existing catalogue."""
        # TODO: implement incremental update
        pass

    def stats(self, dataset: Optional[str] = None, verbose: bool = False, output: Optional[Union[str, Path]] = None) -> dict:
        # TODO: implement stats
        return {}

    def backup(self, backup_dir: Optional[Union[str, Path]] = None) -> Path:
        # TODO: implement backup
        return Path()

    def query(self, safe_name: str) -> Optional[dict]:
        # TODO: implement query
        return None

    def get_centroids(self) -> pl.DataFrame:
        return create_empty_catalogue()

    def _load_catalogue(self) -> pl.DataFrame:
        return create_empty_catalogue()

    def _save_catalogue(self, df: pl.DataFrame) -> None:
        pass

    def _merge_updates(self, new_rows: pl.DataFrame) -> pl.DataFrame:
        return create_empty_catalogue()