"""Core catalogue class for s1iw_catalogue."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any, Optional

import polars as pl

from s1iw_catalogue.config import load_config
from s1iw_catalogue.schema import create_empty_catalogue
from s1iw_catalogue.updater import CatalogueUpdater
from s1iw_catalogue.stats import CatalogueStats

# Set up module-level logger
logger = logging.getLogger(__name__)

# # Ensure the logger has a handler (similar to updater.py)
# if not logger.handlers:
#     handler = logging.StreamHandler()
#     formatter = logging.Formatter(
#         "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
#     )
#     handler.setFormatter(formatter)
#     logger.addHandler(handler)
#     logger.setLevel(logging.INFO)


class S1IWCatalogue:
    def __init__(
        self,
        catalogue_path: str | Path,
        config: str | Path | dict[str, Any] | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        self._catalogue_path = Path(catalogue_path)
        # Resolve config path to absolute
        if config_path:
            self._config_path = Path(config_path).resolve()
        elif isinstance(config, (str, Path)):
            self._config_path = Path(config).resolve()
        else:
            self._config_path = None

        # Load config
        if isinstance(config, (str, Path)):
            self._config = load_config(config_path=config)
        else:
            self._config = load_config() if config is None else config

        self._updater = CatalogueUpdater(config=self._config, config_path=self._config_path)  # type: ignore[arg-type]

    def _write_parquet_with_metadata(self, df: pl.DataFrame, path: Path) -> None:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq

            table = df.to_arrow()

            # Merge new metadata with any existing metadata
            existing_metadata = table.schema.metadata or {}
            new_metadata = {
                **existing_metadata,
                b"config_file": str(self._config_path).encode() if self._config_path else b"unknown"
            }

            # Attach merged metadata to the table's schema
            table_with_metadata = table.replace_schema_metadata(new_metadata)

            pq.write_table(
                table_with_metadata,
                path,
                compression="snappy",
            )

            logger.info(f"Written parquet with config metadata: {path}")
            logger.info(f"  metadata: {new_metadata}")

        except Exception as e:
            logger.warning(f"PyArrow write with metadata failed: {e}. Falling back to polars without metadata.")
            df.write_parquet(path, compression="snappy")

    def create(self, output_path: str | Path | None = None) -> None:
        """Create a brand new catalogue from scratch."""
        out_path = Path(output_path) if output_path else self._catalogue_path
        reference_listings = self._config.get("paths", {}).get("reference_listings", {})
        df = self._updater.build_from_listings(reference_listings)
        df = self._updater.core_update(df)
        df = self._updater._compute_category_and_conflicts(df, reference_listings, out_path)
        self._write_parquet_with_metadata(df, out_path)
        logger.info(f"Catalogue created at {out_path}")

    def update(self, force_meteo_refresh: bool = False) -> None:
        """
        Incrementally update the existing catalogue.

        Behavior:
        - Existing rows: preserve all columns except:
          - datasets: merge new dataset names
          - horodating: update if row changed
          - presence columns: fill if empty (not overwrite)
          - polygon/S3path: fill if empty (not overwrite)
        - New rows: append with full pipeline
        - Rows that become linked: merge and update horodating
        """
        logger.info(f"Updating catalogue at {self._catalogue_path}...")

        if not self._catalogue_path.exists():
            logger.error(f"Catalogue file not found: {self._catalogue_path}")
            return

        existing_df = pl.read_parquet(self._catalogue_path)
        logger.info(f"Loaded existing catalogue with {existing_df.height} rows.")

        reference_listings = self._config.get("paths", {}).get("reference_listings", {})
        logger.info("Building new rows from listings...")
        new_df = self._updater.build_from_listings(reference_listings)
        logger.info(f"Built {new_df.height} rows from listings.")

        existing_slc = set(
            existing_df.filter(pl.col("SAFE SLC").is_not_null())["SAFE SLC"].to_list()
        )
        existing_grd = set(
            existing_df.filter(pl.col("SAFE GRD").is_not_null())["SAFE GRD"].to_list()
        )

        rows_to_merge = []
        rows_to_append = []

        for row in new_df.to_dicts():
            slc = row.get("SAFE SLC")
            grd = row.get("SAFE GRD")
            is_existing = (slc and slc in existing_slc) or (grd and grd in existing_grd)
            if is_existing:
                rows_to_merge.append(row)
            else:
                rows_to_append.append(row)

        logger.info(
            f"Found {len(rows_to_merge)} existing rows to merge, {len(rows_to_append)} new rows to append."
        )

        if rows_to_merge:
            merge_df = pl.DataFrame(rows_to_merge, schema=existing_df.schema)

            existing_df = existing_df.with_columns(
                pl.when(pl.col("SAFE SLC").is_not_null())
                .then(pl.col("SAFE SLC"))
                .otherwise(pl.col("SAFE GRD"))
                .alias("_join_key")
            )
            merge_df = merge_df.with_columns(
                pl.when(pl.col("SAFE SLC").is_not_null())
                .then(pl.col("SAFE SLC"))
                .otherwise(pl.col("SAFE GRD"))
                .alias("_join_key")
            )

            merged = existing_df.join(
                merge_df.select(["_join_key", "datasets"]),
                on="_join_key",
                how="left",
                suffix="_new",
            )

            merged = merged.with_columns(
                pl.concat_list(
                    pl.col("datasets"),
                    pl.col("datasets_new"),
                )
                .list.unique()
                .alias("datasets")
            )
            merged = merged.with_columns(
                pl.when(pl.col("datasets_new").list.len() > 0)
                .then(pl.lit(datetime.datetime.now()))
                .otherwise(pl.col("horodating"))
                .alias("horodating")
            )
            merged = merged.drop(["_join_key", "datasets_new"])

            merged = self._updater.core_upate(merged)
            existing_df = merged
            logger.info(f"Merged {len(rows_to_merge)} existing rows.")

        if rows_to_append:
            append_df = pl.DataFrame(rows_to_append, schema=existing_df.schema)
            append_df = self._updater.core_upate(append_df)
            existing_df = pl.concat([existing_df, append_df], how="vertical_relaxed")
            logger.info(f"Appended {len(rows_to_append)} new rows.")

        # Compute category after merging all rows
        existing_df = self._updater._compute_category_and_conflicts(
            existing_df,
            reference_listings,
            self._catalogue_path
        )

        existing_df = existing_df.unique()

        # Write with metadata
        temp_path = self._catalogue_path.with_suffix(".parquet.tmp")
        self._write_parquet_with_metadata(existing_df, temp_path)
        temp_path.rename(self._catalogue_path)

        logger.info(f"Update complete. Final catalogue has {existing_df.height} rows.")
        logger.info(f"Path: {self._catalogue_path}")

    def merge(self, input_paths: list[Path], output_path: Path) -> None:
        """Merge multiple catalogues into one."""
        self._updater.merge_catalogues(input_paths, output_path, self._config_path)

    def stats(self, dataset: str | None = None, verbose: bool = False, output: str | Path | None = None) -> dict[str, Any]:
        df = self._load_catalogue()
        if dataset:
            df = df.filter(pl.col("datasets").list.contains(dataset))
            if df.height == 0:
                logger.warning(f"No products found for dataset '{dataset}'")
                return {}
        stats_obj = CatalogueStats(df)
        result = stats_obj.to_dict()
        if output:
            stats_obj.to_json(Path(output))
            logger.info(f"Statistics exported to {output}")
        if verbose:
            print(stats_obj.to_string())
        return result

    def backup(self, backup_dir: str | Path | None = None) -> Path:
        # TODO: implement backup
        return Path()

    def query(self, safe_name: str) -> dict[str, Any] | None:
        # TODO: implement query
        return None

    def get_centroids(self) -> pl.DataFrame:
        return create_empty_catalogue()

    def _load_catalogue(self) -> pl.DataFrame:
        """Load the catalogue from the stored path."""
        if not self._catalogue_path.exists():
            raise FileNotFoundError(f"Catalogue not found: {self._catalogue_path}")
        return pl.read_parquet(self._catalogue_path)

    def _save_catalogue(self, df: pl.DataFrame) -> None:
        pass

    def _merge_updates(self, new_rows: pl.DataFrame) -> pl.DataFrame:
        return create_empty_catalogue()