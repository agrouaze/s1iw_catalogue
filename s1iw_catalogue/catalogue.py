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

# Set up module-level logger
logger = logging.getLogger(__name__)


class S1IWCatalogue:
    """Main class for managing the Sentinel-1 IW exhaustive catalogue."""

    def __init__(
        self,
        catalogue_path: str | Path,
        config: str | Path | dict[str, Any] | None = None,
    ) -> None:
        self._catalogue_path = Path(catalogue_path)
        self._config = load_config() if config is None else config
        self._updater = CatalogueUpdater(self._config)  # type: ignore[arg-type]

    def create(self, output_path: str | Path | None = None) -> None:
        """Create a brand new catalogue from scratch."""
        out_path = Path(output_path) if output_path else self._catalogue_path
        # Get listing configurations (can be string, list, or directory)
        slc_listings = self._config.get("paths", {}).get("reference_listings", {}).get("slc", {})  # type: ignore[union-attr]
        grd_listings = self._config.get("paths", {}).get("reference_listings", {}).get("grd", {})  # type: ignore[union-attr]
        # Build catalogue from listings
        df = self._updater.build_from_listings(slc_listings, grd_listings)
        df = self._updater.link_slc_grd(df)
        # Write to Parquet
        df.write_parquet(out_path, compression="snappy")
        logger.info(f"Catalogue created at {out_path}")

    def update(self, force_meteo_refresh: bool = False) -> None:
        """
        Incrementally update the existing catalogue.

        Behavior:
        - Existing rows: preserve all columns except:
          - dataset(s) d'appartenance: merge new dataset names
          - horodating: update if row changed
          - presence columns: fill if empty (not overwrite)
          - polygon/S3path: fill if empty (not overwrite)
        - New rows: append with full pipeline
        - Rows that become linked: merge and update horodating
        """
        logger.info(f"Updating catalogue at {self._catalogue_path}...")

        # 1. Load existing catalogue
        if not self._catalogue_path.exists():
            logger.error(f"Catalogue file not found: {self._catalogue_path}")
            return

        existing_df = pl.read_parquet(self._catalogue_path)
        logger.info(f"Loaded existing catalogue with {existing_df.height} rows.")

        # 2. Read new listings from config
        slc_listings = self._config.get("paths", {}).get("reference_listings", {}).get("slc", {})  # type: ignore[union-attr]
        grd_listings = self._config.get("paths", {}).get("reference_listings", {}).get("grd", {})  # type: ignore[union-attr]

        # 3. Build new rows from listings (raw, not linked yet)
        logger.info("Building new rows from listings...")
        new_df = self._updater.build_from_listings(slc_listings, grd_listings)
        logger.info(f"Built {new_df.height} rows from listings.")

        # 4. Identify existing SAFE names for lookup
        existing_slc = set(
            existing_df.filter(pl.col("SAFE SLC").is_not_null())["SAFE SLC"].to_list()
        )
        existing_grd = set(
            existing_df.filter(pl.col("SAFE GRD").is_not_null())["SAFE GRD"].to_list()
        )

        # 5. Separate new rows into: existing (to merge) and truly new (to append)
        rows_to_merge = []  # rows that already exist (need dataset merge)
        rows_to_append = []  # rows that are completely new

        for row in new_df.to_dicts():
            slc = row.get("SAFE SLC")
            grd = row.get("SAFE GRD")

            # Check if this row already exists in the catalogue
            is_existing = (slc and slc in existing_slc) or (grd and grd in existing_grd)

            if is_existing:
                rows_to_merge.append(row)
            else:
                rows_to_append.append(row)

        logger.info(
            f"Found {len(rows_to_merge)} existing rows to merge, {len(rows_to_append)} new rows to append."
        )

        # 6. Merge existing rows: update dataset(s) and horodating
        if rows_to_merge:
            merge_df = pl.DataFrame(rows_to_merge, schema=existing_df.schema)

            # For each existing row, merge dataset arrays and update horodating
            # We need to join on SAFE SLC or SAFE GRD
            # Create a unique key for joining
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

            # Join to merge datasets
            merged = existing_df.join(
                merge_df.select(["_join_key", "dataset(s) d'appartenance"]),
                on="_join_key",
                how="left",
                suffix="_new",
            )

            # Merge dataset arrays (UNION)
            merged = merged.with_columns(
                pl.concat_list(
                    pl.col("dataset(s) d'appartenance"),
                    pl.col("dataset(s) d'appartenance_new"),
                )
                .list.unique()
                .alias("dataset(s) d'appartenance")
            )
            # Update horodating to now if datasets changed
            merged = merged.with_columns(
                pl.when(pl.col("dataset(s) d'appartenance_new").list.len() > 0)
                .then(pl.lit(datetime.datetime.now()))
                .otherwise(pl.col("horodating"))
                .alias("horodating")
            )
            # Drop temporary columns
            merged = merged.drop(["_join_key", "dataset(s) d'appartenance_new"])

            # Run the full pipeline on merged rows to update presence, polygons, etc.
            # Only for rows that were merged (their join key exists in both)
            # But we need to preserve rows that didn't change
            # For simplicity, we run the full pipeline on all rows
            # This will update presence, polygons, etc. for rows that were missing them
            merged = self._updater.link_slc_grd(merged)
            existing_df = merged
            logger.info(f"Merged {len(rows_to_merge)} existing rows.")

        # 7. Append new rows: run full pipeline
        if rows_to_append:
            append_df = pl.DataFrame(rows_to_append, schema=existing_df.schema)
            # Run full pipeline on new rows
            append_df = self._updater.link_slc_grd(append_df)
            # Append to existing
            existing_df = pl.concat([existing_df, append_df], how="vertical_relaxed")
            logger.info(f"Appended {len(rows_to_append)} new rows.")

        # 8. Deduplicate (just in case)
        existing_df = existing_df.unique()

        # 9. Write atomic (temp file then rename)
        temp_path = self._catalogue_path.with_suffix(".parquet.tmp")
        existing_df.write_parquet(temp_path, compression="snappy")
        temp_path.rename(self._catalogue_path)

        logger.info(f"Update complete. Final catalogue has {existing_df.height} rows.")
        logger.info(f"Path: {self._catalogue_path}")

    def stats(
        self,
        dataset: str | None = None,
        verbose: bool = False,
        output: str | Path | None = None,
    ) -> dict[str, Any]:
        # TODO: implement stats
        return {}

    def backup(self, backup_dir: str | Path | None = None) -> Path:
        # TODO: implement backup
        return Path()

    def query(self, safe_name: str) -> dict[str, Any] | None:
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