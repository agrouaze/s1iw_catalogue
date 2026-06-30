"""Incremental update logic for the catalogue."""

from typing import Any, Dict, List, Optional, Tuple

import datetime
import logging
import re
import os
import time
from collections import defaultdict
from pathlib import Path
import hashlib
import polars as pl
import contextlib
from s1iw_catalogue.schema import SCHEMA

# Set up module-level logger
logger = logging.getLogger(__name__)


class CatalogueUpdater:
    """Handles incremental updates of the catalogue."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        # Configure logger if not already configured (optional)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)

    @staticmethod
    def parse_safe_name(safe_name: str) -> dict[str, Any]:
        """
        Parse a SAFE filename using a regular expression.

        Expected format examples:
        S1A_IW_GRDH_1SDV_20190711T181228_20190711T181253_028073_032B9D_6E14.SAFE
        S1B_IW_SLC__1SDV_20190901T164658_20190901T164725_017847_021963_E116.SAFE

        Returns a dictionary with keys:
            safe_name, mission, product_type, polarization, start_date
        """
        # Remove .SAFE suffix
        name = safe_name.removesuffix(".SAFE")
        # Regex pattern:
        # Group1: mission (S1A, S1B, S1C, S1D)
        # Group2: product type (SLC, GRDH, OCN, ...)
        # Group3: polarization (e.g., 1SDV, 1SSV, etc.) – can be empty if double underscore
        # Group4: start date (YYYYMMDDTHHMMSS)
        pattern = r"^(S1[ABCD])_IW_([A-Z]+)_+([0-9A-Z]*)_(\d{8}T\d{6})_(\d{8}T\d{6})"
        match = re.match(pattern, name)
        if not match:
            raise ValueError(f"Unable to parse SAFE name: {safe_name}")

        mission = match.group(1)
        product_type = match.group(2)
        polarization = (
            match.group(3) if match.group(3) else ""
        )  # empty if double underscore
        start_date_str = match.group(4)
        start_date = datetime.datetime.strptime(start_date_str, "%Y%m%dT%H%M%S")
        end_date_str = match.group(5)
        end_date = datetime.datetime.strptime(end_date_str, "%Y%m%dT%H%M%S")
        return {
            "safe_name": safe_name,
            "mission": mission,
            "product_type": product_type,
            "polarization": polarization,
            "start_date": start_date,
            "end_date": end_date,
        }

    def _read_one_listing(self, path: Path) -> pl.DataFrame:
        """Read a single listing file (one SAFE name per line)."""
        logger.debug(f"Reading listing file: {path}")
        if not path.exists():
            logger.warning(f"Listing file does not exist: {path}")
            return pl.DataFrame(
                schema={
                    "safe_name": pl.Utf8,
                    "mission": pl.Utf8,
                    "product_type": pl.Utf8,
                    "polarization": pl.Utf8,
                    "start_date": pl.Datetime,
                }
            )

        lines = path.read_text().strip().splitlines()
        logger.info(f"Found {len(lines)} lines in {path}")
        data = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = self.parse_safe_name(line)
                data.append(parsed)
            except ValueError as e:
                logger.warning(f"Skipping invalid SAFE name: {line} - {e}")
                continue

        if not data:
            logger.warning(f"No valid SAFE names found in {path}")
            return pl.DataFrame(
                schema={
                    "safe_name": pl.Utf8,
                    "mission": pl.Utf8,
                    "product_type": pl.Utf8,
                    "polarization": pl.Utf8,
                    "start_date": pl.Datetime,
                }
            )
        logger.info(f"Successfully parsed {len(data)} entries from {path}")
        return pl.DataFrame(data)

    def read_listings(
        self, listing_paths: Path | str | list[Path | str]
    ) -> pl.DataFrame:
        """Read one or more listing files/directories and concatenate results."""
        if isinstance(listing_paths, (str, Path)):
            listing_paths = [listing_paths]

        all_dfs = []
        for path in listing_paths:
            path = Path(path)
            if path.is_dir():
                logger.info(f"Reading directory: {path}")
                for file in sorted(path.glob("*.*")):
                    if file.suffix in (".txt", ".csv"):
                        all_dfs.append(self._read_one_listing(file))
            else:
                all_dfs.append(self._read_one_listing(path))

        if not all_dfs:
            logger.warning("No listing files found or all were empty")
            return pl.DataFrame(
                schema={
                    "safe_name": pl.Utf8,
                    "mission": pl.Utf8,
                    "product_type": pl.Utf8,
                    "polarization": pl.Utf8,
                    "start_date": pl.Datetime,
                }
            )

        combined = pl.concat(all_dfs, how="vertical_relaxed").unique(
            subset=["safe_name"]
        )
        logger.info(
            f"Total unique SAFE names after combining listings: {combined.height}"
        )
        return combined

    def build_from_listings(
        self,
        listings: dict[str, Any],
    ) -> pl.DataFrame:
        """
        Combine SLC and GRD listings into a catalogue DataFrame (no external queries).

        Expected config structure:
        paths:
        reference_listings:
            dataset_name:
            path: "/path/to/listing.txt"
            type: "slc" | "grd" | "ocn"
            description: "..."   (optional, stored only in config)
            category: "..."      (optional, stored only in config)

        Listings without a valid 'type' or 'path' are skipped with a warning.
        """
        logger.info("Building catalogue from listings...")

        # Separate by type
        slc_paths = []
        grd_paths = []
        ocn_paths = []  # for future use

        for name, info in listings.items():
            if not isinstance(info, dict):
                logger.warning(f"Listing '{name}' is not a dict; skipping.")
                continue

            path = info.get("path")
            ptype = info.get("type", "").lower()

            if not path:
                logger.warning(f"Listing '{name}' has no 'path'; skipping.")
                continue

            if ptype not in ("slc", "grd", "ocn"):
                logger.warning(
                    f"Listing '{name}' has invalid type '{ptype}'; "
                    "must be one of: slc, grd, ocn. Skipping."
                )
                continue

            if ptype == "slc":
                slc_paths.append((name, path))
            elif ptype == "grd":
                grd_paths.append((name, path))
            elif ptype == "ocn":
                ocn_paths.append((name, path))

        # ---------- Build SLC rows ----------
        slc_dfs = []
        if slc_paths:
            logger.info(f"Reading {len(slc_paths)} SLC dataset(s)...")
            for name, path in slc_paths:
                logger.info(f"Reading SLC dataset '{name}' from {path}")
                df_raw = self.read_listings(path)
                if df_raw.height > 0:
                    df_raw = df_raw.with_columns(
                        pl.lit([name], dtype=pl.List(pl.Utf8)).alias(
                            "dataset(s) d'appartenance"
                        )
                    )
                    slc_dfs.append(df_raw)
                else:
                    logger.warning(f"No valid SLC entries found in dataset '{name}'")
        else:
            logger.info("No SLC datasets found in configuration.")

        if not slc_dfs:
            slc_df_raw = pl.DataFrame(
                schema={
                    "safe_name": pl.Utf8,
                    "mission": pl.Utf8,
                    "product_type": pl.Utf8,
                    "polarization": pl.Utf8,
                    "start_date": pl.Datetime,
                    "dataset(s) d'appartenance": pl.List(pl.Utf8),
                }
            )
        else:
            slc_df_raw = pl.concat(slc_dfs, how="vertical_relaxed")

        # Build SLC rows with all required columns
        slc_df = slc_df_raw.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("SAFE GRD"),
            pl.lit(None, dtype=pl.Utf8).alias("SAFE OCN"),
            pl.col("safe_name").alias("SAFE SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("presence SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("presence GRD"),
            pl.lit(None, dtype=pl.Utf8).alias("presence OCN"),
            pl.lit(None, dtype=pl.Utf8).alias("dataset_category"),
            pl.lit(None, dtype=pl.Utf8).alias("presence L1B XSP A21"),
            pl.lit(None, dtype=pl.Utf8).alias("presence L1C XSP B17"),
            pl.lit(None, dtype=pl.Float32).alias("Hs WW3"),
            pl.lit(None, dtype=pl.Float32).alias("Tp WW3"),
            pl.lit(None, dtype=pl.Float32).alias("U10 ecmwf"),
            pl.lit(None, dtype=pl.Float32).alias("v10 ecmwf"),
            pl.col("start_date").alias("start date SAFE"),
            pl.lit(datetime.datetime.now()).alias("horodating"),
            pl.lit(None, dtype=pl.Utf8).alias("polygon SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("polygon GRD"),
            pl.lit(None, dtype=pl.Utf8).alias("S3path SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("S3path GRD"),
            pl.col("polarization").alias("polarization"),
            pl.col("mission").alias("unité"),
        ).select(list(SCHEMA.keys()))

        # ---------- Build GRD rows ----------
        grd_dfs = []
        if grd_paths:
            logger.info(f"Reading {len(grd_paths)} GRD dataset(s)...")
            for name, path in grd_paths:
                logger.info(f"Reading GRD dataset '{name}' from {path}")
                df_raw = self.read_listings(path)
                if df_raw.height > 0:
                    df_raw = df_raw.with_columns(
                        pl.lit([name], dtype=pl.List(pl.Utf8)).alias(
                            "dataset(s) d'appartenance"
                        )
                    )
                    grd_dfs.append(df_raw)
                else:
                    logger.warning(f"No valid GRD entries found in dataset '{name}'")
        else:
            logger.info("No GRD datasets found in configuration.")

        if not grd_dfs:
            grd_df_raw = pl.DataFrame(
                schema={
                    "safe_name": pl.Utf8,
                    "mission": pl.Utf8,
                    "product_type": pl.Utf8,
                    "polarization": pl.Utf8,
                    "start_date": pl.Datetime,
                    "dataset(s) d'appartenance": pl.List(pl.Utf8),
                }
            )
        else:
            grd_df_raw = pl.concat(grd_dfs, how="vertical_relaxed")

        # Build GRD rows with all required columns
        grd_df = grd_df_raw.with_columns(
            pl.col("safe_name").alias("SAFE GRD"),
            pl.lit(None, dtype=pl.Utf8).alias("SAFE SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("SAFE OCN"),
            pl.lit(None, dtype=pl.Utf8).alias("presence SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("presence GRD"),
            pl.lit(None, dtype=pl.Utf8).alias("presence OCN"),
            pl.lit(None, dtype=pl.Utf8).alias("dataset_category"),
            pl.lit(None, dtype=pl.Utf8).alias("presence L1B XSP A21"),
            pl.lit(None, dtype=pl.Utf8).alias("presence L1C XSP B17"),
            pl.lit(None, dtype=pl.Float32).alias("Hs WW3"),
            pl.lit(None, dtype=pl.Float32).alias("Tp WW3"),
            pl.lit(None, dtype=pl.Float32).alias("U10 ecmwf"),
            pl.lit(None, dtype=pl.Float32).alias("v10 ecmwf"),
            pl.col("start_date").alias("start date SAFE"),
            pl.lit(datetime.datetime.now()).alias("horodating"),
            pl.lit(None, dtype=pl.Utf8).alias("polygon SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("polygon GRD"),
            pl.lit(None, dtype=pl.Utf8).alias("S3path SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("S3path GRD"),
            pl.col("polarization").alias("polarization"),
            pl.col("mission").alias("unité"),
        ).select(list(SCHEMA.keys()))

        # ---------- Combine and deduplicate ----------
        combined = pl.concat([slc_df, grd_df], how="vertical_relaxed").unique()
        logger.info(f"Total combined catalogue rows (before dedup): {combined.height}")
        return combined

    def _log_catalogue_summary(self, df: pl.DataFrame, step_name: str) -> None:
        """Log a summary of the catalogue state after each step."""
        total = df.height
        slc_count = df.filter(pl.col("SAFE SLC").is_not_null()).height
        grd_count = df.filter(pl.col("SAFE GRD").is_not_null()).height
        both_count = df.filter(
            pl.col("SAFE SLC").is_not_null() & pl.col("SAFE GRD").is_not_null()
        ).height
        ocn_count = df.filter(pl.col("SAFE OCN").is_not_null()).height

        logger.info(
            f"  📊 {step_name}: {total} rows, {both_count} linked pairs, "
            f"{slc_count - both_count} SLC-only, {grd_count - both_count} GRD-only, {ocn_count} OCN"
        )

    def link_slc_grd(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Link SLC, GRD, and OCN products using multi-step strategy.
        """
        logger.info("=" * 60)
        logger.info("🚀 Starting SLC-GRD-OCN linking pipeline...")
        logger.info("=" * 60)
        start_total = time.time()

        # Step 1: Local SLC-GRD matching
        logger.info("\n📍 Step 1/6: Local SLC-GRD matching...")
        start = time.time()
        df = self._local_link_slc_grd(df)  # type: ignore[assignment]
        elapsed = time.time() - start
        self._log_catalogue_summary(df, "After local matching")
        logger.info(f"✅ Step 1/6 completed in {elapsed:.1f}s")

        # Step 2: CDSE fallback for SLC-GRD orphans
        logger.info("\n📍 Step 2/6: CDSE fallback for SLC-GRD orphans...")
        start = time.time()
        df = self._cdse_fallback_link(df)
        df = self._merge_linked_rows(df)
        elapsed = time.time() - start
        self._log_catalogue_summary(df, "After CDSE fallback")
        logger.info(f"✅ Step 2/6 completed in {elapsed:.1f}s")

        # Step 3: Link OCN to GRD (primary)
        logger.info("\n📍 Step 3/6: Linking OCN to GRD products...")
        start = time.time()
        df = self._link_ocn_to_grd(df)
        elapsed = time.time() - start
        self._log_catalogue_summary(df, "After OCN-GRD linking")
        logger.info(f"✅ Step 3/6 completed in {elapsed:.1f}s")

        # Step 4: Fallback - Link OCN to SLC
        logger.info("\n📍 Step 4/6: Fallback - Linking OCN to SLC...")
        start = time.time()
        df = self._link_ocn_to_slc(df)
        elapsed = time.time() - start
        self._log_catalogue_summary(df, "After OCN-SLC fallback")
        logger.info(f"✅ Step 4/6 completed in {elapsed:.1f}s")

        # Step 5: Fetch polygons and S3 paths from CDSE
        logger.info("\n📍 Step 5/6: Fetching polygons and S3 paths from CDSE...")
        start = time.time()
        df = self._update_polygons_and_s3paths(df)
        elapsed = time.time() - start
        self._log_catalogue_summary(df, "After polygon fetch")
        logger.info(f"✅ Step 5/6 completed in {elapsed:.1f}s")

        # Step 6: Check presence on Ifremer storage (including OCN)
        logger.info("\n📍 Step 6/6: Checking presence on Ifremer storage...")
        start = time.time()
        df = self._update_presence_columns(df, force=False)
        elapsed = time.time() - start
        self._log_catalogue_summary(df, "After presence check")
        logger.info(f"✅ Step 6/6 completed in {elapsed:.1f}s")

        total_elapsed = time.time() - start_total
        logger.info("=" * 60)
        logger.info(f"🏁 SLC-GRD-OCN linking complete in {total_elapsed:.1f}s")
        logger.info(f"📊 Final catalogue shape: {df.shape}")
        logger.info("=" * 60)

        return df




    def _batch_cdse_match(
        self,
        source_ids: list[str],
        target_type: str,
        output_file: str | None = None,
        checkpoint_dir: Path | None = None,
        cleanup_on_success: bool = False,
    ) -> dict[str, str]:
        if not source_ids:
            return {}

        from cdsodatacli.scripts.match_s1_product_types import entrypoint

        if checkpoint_dir is None:
            checkpoint_dir = self._get_checkpoint_dir()

        if output_file is None:
            # Deterministic filename based on sorted IDs and target type
            sorted_ids = sorted(source_ids)
            hash_obj = hashlib.md5(''.join(sorted_ids).encode())
            hash_hex = hash_obj.hexdigest()[:8]
            output_file = f"batch_{target_type}_{hash_hex}.txt"
            # Place it in the checkpoint directory (or temp)
            output_file = str(Path(checkpoint_dir) / output_file) if checkpoint_dir else output_file

        results = entrypoint(
            safe_list=source_ids,
            target_type=target_type,
            output_filename=output_file,
            logger=logger,
            checkpoint_dir=str(checkpoint_dir) if checkpoint_dir else None,
        )

        mapping = {}
        for r in results:
            if "target_name" in r and "source_id" in r:
                mapping[r["source_id"]] = r["target_name"]

        # Optionally remove the output file if you don't need it
        if output_file and Path(output_file).exists():
            Path(output_file).unlink()

        return mapping


    def _local_link_slc_grd(self, df: pl.DataFrame) -> pl.DataFrame | None:
        """
        Match SLC and GRD using data take ID (relative_orbit + orbit_number).

        Strategy:
        1. Extract data_take_id by looking for the orbit pattern
        2. Match SLC and GRD with same mission, polarization, and data_take_id
        3. Within matches, find the closest time (within ±5 seconds)
        """
        logger.info("Step 1: Local SLC-GRD matching...")

        # Get rows that need linking
        grd_rows = df.filter(
            pl.col("SAFE GRD").is_not_null() & pl.col("SAFE SLC").is_null()
        )
        slc_rows = df.filter(
            pl.col("SAFE SLC").is_not_null() & pl.col("SAFE GRD").is_null()
        )

        logger.info(f"GRD rows needing linking: {grd_rows.height}")
        logger.info(f"SLC rows needing linking: {slc_rows.height}")

        if grd_rows.height == 0 and slc_rows.height == 0:
            logger.info("All rows already linked.")
            return df

        # Extract data_take_id from SAFE name using a robust method
        def extract_data_take_id(safe_name: str) -> str:
            """Extract the data_take_id (orbit_number_relative_orbit) from any SAFE name."""
            if not safe_name:
                return ""
            name = safe_name.removesuffix(".SAFE")
            parts = name.split("_")

            # The orbit pattern is typically: 6 digits_6 hex chars (e.g., 020609_02710E)
            import re

            orbit_pattern = r"(_\d{6}_[A-F0-9]{6}_)"
            match = re.search(orbit_pattern, name)
            if match:
                return match.group(1)
            return ""

        def extract_start_time(safe_name: str) -> datetime.datetime | None:
            """Extract start datetime from SAFE name."""
            if not safe_name:
                return None
            name = safe_name.removesuffix(".SAFE")
            parts = name.split("_")

            # Look for timestamp pattern (YYYYMMDDTHHMMSS)
            import re

            timestamp_pattern = r"(\d{8}T\d{6})"
            matches = re.findall(timestamp_pattern, name)
            if matches:
                try:
                    return datetime.datetime.strptime(matches[0], "%Y%m%dT%H%M%S")
                except ValueError:
                    return None

        # Add columns to DataFrames
        grd_rows = grd_rows.with_columns(
            [
                pl.col("SAFE GRD")
                .map_elements(extract_data_take_id, return_dtype=pl.Utf8)
                .alias("data_take_id"),
                pl.col("SAFE GRD")
                .map_elements(extract_start_time, return_dtype=pl.Datetime)
                .alias("start_time"),
            ]
        )
        slc_rows = slc_rows.with_columns(
            [
                pl.col("SAFE SLC")
                .map_elements(extract_data_take_id, return_dtype=pl.Utf8)
                .alias("data_take_id"),
                pl.col("SAFE SLC")
                .map_elements(extract_start_time, return_dtype=pl.Datetime)
                .alias("start_time"),
            ]
        )

        # Log sample data take IDs
        grd_samples = grd_rows["data_take_id"].head(3).to_list()
        slc_samples = slc_rows["data_take_id"].head(3).to_list()
        logger.info(f"GRD data_take_id samples: {grd_samples}")
        logger.info(f"SLC data_take_id samples: {slc_samples}")

        # Build dictionaries keyed by (mission, polarization, data_take_id) for exact matching
        slc_dict: dict[tuple[str, str, str], list[tuple[str, datetime.datetime]]] = (
            {}
        )  # (mission, pol, data_take_id) -> list of (slc_name, start_time)
        for row in slc_rows.to_dicts():
            mission = row.get("unité", "")
            pol = row.get("polarization", "")
            data_take_id = row.get("data_take_id", "")
            start_time = row.get("start_time")

            if mission and pol and data_take_id:
                key = (mission, pol, data_take_id)
            if key not in slc_dict:
                slc_dict[key] = []
                slc_dict[key].append(
                    (
                        row["SAFE SLC"],
                        start_time if start_time else datetime.datetime.min,
                    )
                )

        updates = {}
        matched_count = 0

        # For each GRD, find best matching SLC
        for grd_row in grd_rows.to_dicts():
            grd_name = grd_row["SAFE GRD"]
            grd_mission = grd_row.get("unité", "")
            grd_pol = grd_row.get("polarization", "")
            grd_data_take_id = grd_row.get("data_take_id", "")
            grd_start_time = grd_row.get("start_time")

            if not grd_mission or not grd_pol or not grd_data_take_id:
                logger.warning(f"GRD missing metadata: {grd_name}")
                continue

            key = (grd_mission, grd_pol, grd_data_take_id)

            if key not in slc_dict:
                logger.warning(f"No SLC found for GRD {grd_name} (key={key})")
                continue

            # Find SLC with closest time (within ±5 seconds)
            best_match = None
            best_time_diff = 999.0

            for slc_info in slc_dict[key]:
                slc_name = slc_info[0]
                slc_start_time = slc_info[1]

                if grd_start_time is not None and slc_start_time is not None:
                    time_diff = abs((grd_start_time - slc_start_time).total_seconds())

                    if time_diff <= 5.0 and time_diff < best_time_diff:
                        best_time_diff = time_diff
                        best_match = slc_name

            if best_match is not None:
                updates[grd_name] = best_match
                matched_count += 1
                logger.debug(
                    f"Local match: GRD {grd_name} -> SLC {best_match} "
                    f"(data_take_id={grd_data_take_id}, time_diff={best_time_diff:.1f}s)"
                )
            else:
                # Check if there's any SLC with same data_take_id but time diff > 5s
                if key in slc_dict:
                    first_slc = slc_dict[key][0][0]
                    logger.warning(
                        f"GRD {grd_name}: No SLC within ±5s. "
                        f"Closest available SLC: {first_slc} (data_take_id={grd_data_take_id})"
                    )

        # Apply updates to the DataFrame
        for grd_name, slc_name in updates.items():
            df = df.with_columns(
                pl.when(pl.col("SAFE GRD") == grd_name)
                .then(pl.lit(slc_name))
                .otherwise(pl.col("SAFE SLC"))
                .alias("SAFE SLC")
            )
            df = df.with_columns(
                pl.when(pl.col("SAFE SLC") == slc_name)
                .then(pl.lit(grd_name))
                .otherwise(pl.col("SAFE GRD"))
                .alias("SAFE GRD")
            )

        # After the matching loop, compute counts
        total_grd_needing = grd_rows.height
        matched_count = len(updates)  # number of GRD entries that got linked
        percentage = (
            (matched_count / total_grd_needing * 100) if total_grd_needing > 0 else 0.0
        )

        logger.info(
            f"Step 1 complete: {matched_count}/{total_grd_needing} GRD entries linked locally ({percentage:.1f}%)"
        )
        return df

    def _extract_data_take(self, safe_name: str) -> str:
        """
        Extract the data take identifier from a SAFE name.
        Example: S1A_IW_SLC__1SDV_20190711T181227_20190711T181254_028073_032B9D_CC09.SAFE
        Returns: 028073_032B9D
        """
        name = safe_name.removesuffix(".SAFE")
        parts = name.split("_")
        if len(parts) >= 7:
            # Return the parts at indices 5 and 6 (0-based)
            return f"{parts[5]}_{parts[6]}"
        return ""

    def _extract_base_pattern(self, safe_name: str) -> str:
        """
        Extract the base pattern without suffix.
        """
        name = safe_name.removesuffix(".SAFE")
        parts = name.split("_")
        if len(parts) >= 7:
            # Return parts before the data take identifier
            return "_".join(parts[:5])
        return name

    def _get_base_pattern(self, safe_name: str, product_type: str) -> str:
        """Extract the base pattern of a SAFE name without the timestamp."""
        # Remove .SAFE suffix
        name = safe_name.removesuffix(".SAFE")
        parts = name.split("_")
        if len(parts) < 9:
            return ""
        # Return parts before the timestamp
        return "_".join(parts[:4])  # mission, IW, product_type, polarization

    def _grd_to_slc_pattern_with_offset(
        self, grd_name: str, offset_seconds: int
    ) -> str:
        """
        Convert GRD naming pattern to expected SLC pattern with a time offset.
        offset_seconds can be negative or positive.
        """
        slc_name = grd_name.replace("_GRDH_", "_SLC__").replace("_GRDH", "_SLC_")

        def adjust_timestamp(match):
            dt = datetime.datetime.strptime(match.group(0), "%Y%m%dT%H%M%S")
            dt = dt + datetime.timedelta(seconds=offset_seconds)
            return dt.strftime("%Y%m%dT%H%M%S")

        slc_name = re.sub(r"\d{8}T\d{6}", adjust_timestamp, slc_name, count=1)
        return slc_name

    def _slc_to_grd_pattern_with_offset(
        self, slc_name: str, offset_seconds: int
    ) -> str:
        """
        Convert SLC naming pattern to expected GRD pattern with a time offset.
        offset_seconds can be negative or positive.
        """
        grd_name = slc_name.replace("_SLC__", "_GRDH_").replace("_SLC_", "_GRDH")

        def adjust_timestamp(match):
            dt = datetime.datetime.strptime(match.group(0), "%Y%m%dT%H%M%S")
            dt = dt + datetime.timedelta(seconds=offset_seconds)
            return dt.strftime("%Y%m%dT%H%M%S")

        grd_name = re.sub(r"\d{8}T\d{6}", adjust_timestamp, grd_name, count=1)
        return grd_name

    def _cdse_fallback_link(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        For rows still missing links, query CDSE using cdsodatacli.
        Now uses the multithreaded entrypoint for GRD→SLC and SLC→GRD in batches.
        """
        logger.info("Step 2: CDSE fallback for orphan products...")

        grd_orphans = df.filter(
            pl.col("SAFE GRD").is_not_null() & pl.col("SAFE SLC").is_null()
        )
        slc_orphans = df.filter(
            pl.col("SAFE SLC").is_not_null() & pl.col("SAFE GRD").is_null()
        )

        total_orphans = grd_orphans.height + slc_orphans.height
        if total_orphans == 0:
            logger.info("No orphans to resolve via CDSE")
            return df

        logger.info(
            f"Found {grd_orphans.height} GRD orphans and {slc_orphans.height} SLC orphans (total {total_orphans})"
        )

        # Initialize mapping variables to avoid UnboundLocalError
        mapping_grd_to_slc = {}
        mapping_slc_to_grd = {}

        # Process GRD→SLC in batch
        if grd_orphans.height > 0:
            grd_ids = [row["SAFE GRD"] for row in grd_orphans.to_dicts()]
            logger.info(f"Batch matching {len(grd_ids)} GRD orphans to SLC...")
            mapping_grd_to_slc = self._batch_cdse_match(grd_ids, "SLC_")
            logger.info(f"Found SLC for {len(mapping_grd_to_slc)}/{len(grd_ids)} GRD orphans")
            for grd_name, slc_name in mapping_grd_to_slc.items():
                df = df.with_columns(
                    pl.when(pl.col("SAFE GRD") == grd_name)
                    .then(pl.lit(slc_name))
                    .otherwise(pl.col("SAFE SLC"))
                    .alias("SAFE SLC")
                )
                df = df.with_columns(
                    pl.when(pl.col("SAFE SLC") == slc_name)
                    .then(pl.lit(grd_name))
                    .otherwise(pl.col("SAFE GRD"))
                    .alias("SAFE GRD")
                )

        # Process SLC→GRD in batch
        if slc_orphans.height > 0:
            slc_ids = [row["SAFE SLC"] for row in slc_orphans.to_dicts()]
            already_linked = set(mapping_grd_to_slc.values())
            slc_ids_to_match = [s for s in slc_ids if s not in already_linked]
            if slc_ids_to_match:
                logger.info(f"Batch matching {len(slc_ids_to_match)} SLC orphans to GRD...")
                mapping_slc_to_grd = self._batch_cdse_match(slc_ids_to_match, "GRDH")
                logger.info(
                    f"Found GRD for {len(mapping_slc_to_grd)}/{len(slc_ids_to_match)} SLC orphans"
                )
                for slc_name, grd_name in mapping_slc_to_grd.items():
                    df = df.with_columns(
                        pl.when(pl.col("SAFE SLC") == slc_name)
                        .then(pl.lit(grd_name))
                        .otherwise(pl.col("SAFE GRD"))
                        .alias("SAFE GRD")
                    )
                    df = df.with_columns(
                        pl.when(pl.col("SAFE GRD") == grd_name)
                        .then(pl.lit(slc_name))
                        .otherwise(pl.col("SAFE SLC"))
                        .alias("SAFE SLC")
                    )

        total_updates = len(mapping_grd_to_slc) + len(mapping_slc_to_grd)
        resolved_percentage = (
            (total_updates / total_orphans * 100) if total_orphans > 0 else 0.0
        )
        logger.info(
            f"Step 2 complete: {total_updates}/{total_orphans} orphan entries resolved via CDSE ({resolved_percentage:.1f}%)"
        )
        return df

    def _call_cdse_get_parent_slc(self, grd_name: str) -> str | None:
        """
        Query CDSE to find the parent SLC for a given GRD.
        Uses cdsodatacli.scripts.match_s1_product_types.find_product_for_safe.
        """
        try:
            from cdsodatacli.scripts.match_s1_product_types import find_product_for_safe
        except ImportError as e:
            logger.warning(f"cdsodatacli not installed: {e}. CDSE fallback disabled.")
            return None

        target_type = "SLC_"  # Valid type for SLC
        delta_dist: defaultdict[str, int] = defaultdict(int)

        try:
            result = find_product_for_safe(
                source_id=grd_name,
                target_type=target_type,
                logger=logger,
                delta_distribution=delta_dist,
            )
            if result and isinstance(result, dict) and "target_name" in result:
                return str(result["target_name"])
            else:
                note = (
                    result.get("note", "unknown reason")
                    if isinstance(result, dict)
                    else "unknown reason"
                )
                logger.warning(f"CDSE did not find SLC for {grd_name}: {note}")
                return None
        except Exception as e:
            logger.error(f"CDSE query failed for {grd_name}: {e}")
            return None

    def _call_cdse_get_derived_grd(self, slc_name: str) -> str | None:
        """
        Query CDSE to find a derived GRD for a given SLC.
        """
        try:
            from cdsodatacli.scripts.match_s1_product_types import find_product_for_safe
        except ImportError as e:
            logger.warning(f"cdsodatacli not installed: {e}. CDSE fallback disabled.")
            return None

        target_type = "GRDH"  # Valid type for GRD
        delta_dist: defaultdict[str, int] = defaultdict(int)

        try:
            result = find_product_for_safe(
                source_id=slc_name,
                target_type=target_type,
                logger=logger,
                delta_distribution=delta_dist,
            )
            if result and isinstance(result, dict) and "target_name" in result:
                return str(result["target_name"])
            else:
                note = (
                    result.get("note", "unknown reason")
                    if isinstance(result, dict)
                    else "unknown reason"
                )
                logger.warning(f"CDSE did not find GRD for {slc_name}: {note}")
                return None
        except Exception as e:
            logger.error(f"CDSE query failed for {slc_name}: {e}")
            return None
        

    def _get_category_priority(self, category: str) -> int:
        """Return priority (higher = more important) for category."""
        priorities = {"undefined": 0, "train": 1, "val": 2, "test": 3}
        return priorities.get(category.lower(), 0)

    def _compute_category_and_conflicts(
        self,
        df: pl.DataFrame,
        dataset_metadata: dict[str, dict],
        output_path: Path | None = None,
    ) -> pl.DataFrame:
        """
        Add dataset_category column based on dataset list and priority hierarchy.
        Writes conflict report if multiple categories conflict.
        """
        # Build mapping: dataset_name -> category
        dataset_category_map = {}
        for name, info in dataset_metadata.items():
            if isinstance(info, dict) and "category" in info:
                dataset_category_map[name] = info["category"]
            else:
                dataset_category_map[name] = "undefined"

        # Process each row
        new_categories = []
        conflicts = []

        for row in df.to_dicts():
            datasets = row.get("dataset(s) d'appartenance", [])
            if not datasets:
                new_categories.append("undefined")
                continue

            # Collect unique categories with priorities
            cat_set = set()
            for ds in datasets:
                cat = dataset_category_map.get(ds, "undefined")
                cat_set.add(cat)

            # If only one category, use it
            if len(cat_set) == 1:
                new_categories.append(cat_set.pop())
            else:
                # Choose highest priority
                best_cat = max(cat_set, key=self._get_category_priority)
                new_categories.append(best_cat)

                # Log conflict if more than one distinct category
                if len(cat_set) > 1:
                    safe_name = row.get("SAFE SLC") or row.get("SAFE GRD") or row.get("SAFE OCN")
                    conflicts.append({
                        "safe": safe_name,
                        "datasets": datasets,
                        "categories": list(cat_set),
                        "chosen": best_cat,
                    })

        # Add column
        df = df.with_columns(pl.Series(new_categories).alias("dataset_category"))

        # Write conflicts if any and output_path provided
        if conflicts and output_path:
            self._write_conflicts(conflicts, output_path)

        return df

    def _write_conflicts(self, conflicts: list[dict], catalogue_path: Path) -> None:
        """Write conflict report to a file in the same directory as the catalogue."""
        import json
        from datetime import datetime

        conflict_dir = catalogue_path.parent
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        conflict_file = conflict_dir / f"conflicts_{timestamp}.txt"

        with open(conflict_file, "w") as f:
            f.write(f"Catalogue: {catalogue_path}\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write("=" * 60 + "\n")
            f.write(f"Total conflicts: {len(conflicts)}\n")
            f.write("-" * 60 + "\n")
            for c in conflicts:
                f.write(f"SAFE: {c['safe']}\n")
                f.write(f"  Datasets: {c['datasets']}\n")
                f.write(f"  Categories: {c['categories']}\n")
                f.write(f"  Chosen: {c['chosen']}\n")
                f.write("\n")

        logger.info(f"Conflict report written to {conflict_file}")

    # def find_new_safe(
    #     self,
    #     existing_df: pl.DataFrame,
    #     slc_listing: str | Path | list[str],
    #     grd_listing: str | Path | list[str],
    # ) -> pl.DataFrame:
    #     """Identify SAFE not yet present in the catalogue."""
    #     new_raw = self.build_from_listings(slc_listing if isinstance(slc_listing, (str, Path, list, dict)) else [], grd_listing if isinstance(grd_listing, (str, Path, list, dict)) else [])  # type: ignore[arg-type]
    #     if existing_df.height == 0:
    #         return new_raw

    #     existing_slc = set(
    #         existing_df.filter(pl.col("SAFE SLC").is_not_null())["SAFE SLC"].to_list()
    #     )
    #     existing_grd = set(
    #         existing_df.filter(pl.col("SAFE GRD").is_not_null())["SAFE GRD"].to_list()
    #     )

    #     new_rows = []
    #     for row in new_raw.to_dicts():
    #         if row["SAFE SLC"] and row["SAFE SLC"] not in existing_slc:
    #             new_rows.append(row)
    #         elif row["SAFE GRD"] and row["SAFE GRD"] not in existing_grd:
    #             new_rows.append(row)

    #     if not new_rows:
    #         logger.info("No new SAFE found.")
    #         return pl.DataFrame(schema=SCHEMA)
    #     logger.info(f"Found {len(new_rows)} new SAFE entries.")
    #     return pl.DataFrame(new_rows, schema=SCHEMA)

    def _merge_linked_rows(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        For rows that have both SLC and GRD filled, merge column values according to rules.
        """
        logger.info("Merging linked SLC-GRD rows...")

        # Split polygon and S3path columns into SLC/GRD variants
        df = self._split_geometry_columns(df)

        # Separate linked and unlinked rows
        linked_rows = df.filter(
            pl.col("SAFE SLC").is_not_null() & pl.col("SAFE GRD").is_not_null()
        )
        unlinked_rows = df.filter(
            ~(pl.col("SAFE SLC").is_not_null() & pl.col("SAFE GRD").is_not_null())
        )

        if linked_rows.height == 0:
            logger.info("No linked rows to merge.")
            return df

        logger.info(f"Found {linked_rows.height} rows with both SLC and GRD.")
        logger.info(f"Keeping {unlinked_rows.height} unlinked rows unchanged.")

        rows = linked_rows.to_dicts()

        merged_rows = []
        # Group by (SAFE SLC, SAFE GRD) pair
        pairs: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in rows:
            key = (row["SAFE SLC"], row["SAFE GRD"])
            if key not in pairs:
                pairs[key] = []
            pairs[key].append(row)

        for (slc, grd), rows_list in pairs.items():
            # Start with the first row as base
            merged = rows_list[0].copy()

            # Merge datasets from all rows
            all_datasets = set()
            for r in rows_list:
                datasets = r.get("dataset(s) d'appartenance", [])
                if datasets:
                    all_datasets.update(datasets)
            merged["dataset(s) d'appartenance"] = list(all_datasets)

            # Merge meteo: take first non-null
            for meteo_col in ["Hs WW3", "Tp WW3", "U10 ecmwf", "v10 ecmwf"]:
                for r in rows_list:
                    val = r.get(meteo_col)
                    if val is not None:
                        merged[meteo_col] = val
                        break

            # start date: take the minimum (earliest)
            start_dates = [
                r.get("start date SAFE")
                for r in rows_list
                if r.get("start date SAFE") is not None
            ]
            if start_dates:
                merged["start date SAFE"] = min(d for d in start_dates if d is not None)

            # horodating: take the maximum (most recent)
            horodatings = [
                r.get("horodating")
                for r in rows_list
                if r.get("horodating") is not None
            ]
            if horodatings:
                merged["horodating"] = max(d for d in horodatings if d is not None)

            # polygon SLC/GRD: take first non-null
            for poly_col in ["polygon SLC", "polygon GRD", "S3path SLC", "S3path GRD"]:
                for r in rows_list:
                    val = r.get(poly_col)
                    if val is not None:
                        merged[poly_col] = val
                        break

            # --- FIX: Merge OCN-related columns by taking first non-null ---
            # SAFE OCN: first non-null from any row
            safe_ocn_val = None
            for r in rows_list:
                val = r.get("SAFE OCN")
                if val is not None:
                    safe_ocn_val = val
                    break
            merged["SAFE OCN"] = safe_ocn_val

            # presence OCN: first non-null from any row
            presence_ocn_val = None
            for r in rows_list:
                val = r.get("presence OCN")
                if val is not None:
                    presence_ocn_val = val
                    break
            merged["presence OCN"] = presence_ocn_val


            # Merge dataset_category: take highest priority
            cat1 = merged.get("dataset_category")
            cat2 = rows_list[1].get("dataset_category") if len(rows_list) > 1 else None  # but we need to consider all rows
            # Actually we should consider all rows in the group:
            all_cats = []
            for r in rows_list:
                cat = r.get("dataset_category")
                if cat:
                    all_cats.append(cat)
            if all_cats:
                best_cat = max(all_cats, key=self._get_category_priority)
                merged["dataset_category"] = best_cat
            else:
                merged["dataset_category"] = None

            merged_rows.append(merged)

        # Convert back to DataFrame
        merged_linked = pl.DataFrame(merged_rows, schema=SCHEMA)

        # Ensure both DataFrames have the same column order
        unlinked_rows = unlinked_rows.select(merged_linked.columns)

        # Combine linked (merged) and unlinked rows
        df = pl.concat([merged_linked, unlinked_rows], how="vertical_relaxed")

        logger.info(f"Merging complete. New shape: {df.shape}")
        return df

    def _split_geometry_columns(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Split polygon and S3path into SLC-specific and GRD-specific columns.
        This should be called BEFORE merging linked rows.
        """
        # Check if columns already exist
        if "polygon SLC" in df.columns and "polygon GRD" in df.columns:
            return df

        # Check if the original columns exist
        has_polygon = "polygon of the acquisition from CDSE" in df.columns
        has_s3path = "S3path from CDSE" in df.columns

        if not has_polygon and not has_s3path:
            logger.debug("Geometry columns already split or not present. Skipping.")
            return df

        # Create SLC-specific polygon column
        if has_polygon:
            df = df.with_columns(
                pl.when(pl.col("SAFE SLC").is_not_null())
                .then(pl.col("polygon of the acquisition from CDSE"))
                .otherwise(None)
                .alias("polygon SLC")
            )
            df = df.with_columns(
                pl.when(pl.col("SAFE GRD").is_not_null())
                .then(pl.col("polygon of the acquisition from CDSE"))
                .otherwise(None)
                .alias("polygon GRD")
            )
            df = df.drop(["polygon of the acquisition from CDSE"])
        else:
            # If original doesn't exist, create empty columns
            df = df.with_columns(
                [
                    pl.lit(None, dtype=pl.Utf8).alias("polygon SLC"),
                    pl.lit(None, dtype=pl.Utf8).alias("polygon GRD"),
                ]
            )

        if has_s3path:
            df = df.with_columns(
                pl.when(pl.col("SAFE SLC").is_not_null())
                .then(pl.col("S3path from CDSE"))
                .otherwise(None)
                .alias("S3path SLC")
            )
            df = df.with_columns(
                pl.when(pl.col("SAFE GRD").is_not_null())
                .then(pl.col("S3path from CDSE"))
                .otherwise(None)
                .alias("S3path GRD")
            )
            df = df.drop(["S3path from CDSE"])
        else:
            df = df.with_columns(
                [
                    pl.lit(None, dtype=pl.Utf8).alias("S3path SLC"),
                    pl.lit(None, dtype=pl.Utf8).alias("S3path GRD"),
                ]
            )

        logger.info("Geometry columns split into SLC and GRD variants.")
        return df

    def _update_polygons_and_s3paths(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Query CDSE to get polygon footprints and S3 paths for SAFE products that are missing this info.
        Uses cdsodatacli.query.fetch_data with exact date ranges from the SAFE names.
        Only queries products that don't already have polygon/S3path information.
        Supports caching via cdse_cache_dir configuration.
        """
        logger.info(
            "Fetching polygon footprints and S3 paths from CDSE for missing products..."
        )

        try:
            import geopandas as gpd
            import pandas as pd
            from cdsodatacli.query import fetch_data
            from shapely.geometry import box
        except ImportError as e:
            logger.warning(
                f"cdsodatacli or geopandas not installed: {e}. Skipping polygon fetch."
            )
            return df

        # Get cache directory from config if available
        cache_dir = self.config.get("cdse_cache_dir", None)
        if cache_dir:
            cache_dir = Path(cache_dir)
            logger.info(f"Using CDSE cache directory: {cache_dir}")
            # Ensure cache directory exists
            cache_dir.mkdir(parents=True, exist_ok=True)
        else:
            logger.info("No CDSE cache directory configured. Cache disabled.")

        # Identify products missing polygon or S3path information
        missing_polygon_slc = df.filter(
            pl.col("SAFE SLC").is_not_null() & pl.col("polygon SLC").is_null()
        )
        missing_polygon_grd = df.filter(
            pl.col("SAFE GRD").is_not_null() & pl.col("polygon GRD").is_null()
        )
        missing_s3_slc = df.filter(
            pl.col("SAFE SLC").is_not_null() & pl.col("S3path SLC").is_null()
        )
        missing_s3_grd = df.filter(
            pl.col("SAFE GRD").is_not_null() & pl.col("S3path GRD").is_null()
        )

        # Combine all missing products
        missing_slc = set(missing_polygon_slc["SAFE SLC"].to_list()) | set(
            missing_s3_slc["SAFE SLC"].to_list()
        )
        missing_grd = set(missing_polygon_grd["SAFE GRD"].to_list()) | set(
            missing_s3_grd["SAFE GRD"].to_list()
        )

        all_missing = list(missing_slc | missing_grd)

        if not all_missing:
            logger.info("All products already have polygon and S3path information.")
            return df

        logger.info(
            f"Found {len(all_missing)} products missing polygon or S3path information."
        )

        # Process in batches to avoid overwhelming the API
        batch_size = 50
        all_results = []

        for i in range(0, len(all_missing), batch_size):
            batch_names = all_missing[i : i + batch_size]
            logger.info(
                f"Processing batch {i//batch_size + 1}/{(len(all_missing)-1)//batch_size + 1} ({len(batch_names)} products)"
            )

            records = []
            for safe_name in batch_names:
                try:
                    # Use the existing parse_safe_name method
                    parsed = self.parse_safe_name(safe_name)
                    start_date = parsed["start_date"]
                    end_date = parsed["end_date"]
                    # mission = parsed["mission"]
                    product_type = parsed["product_type"]

                    # Explicitly set the product type filter to match the product type
                    # For SLC products, the product type is "SLC_" in CDSE
                    # For GRD products, it's "GRD"
                    if product_type.upper() == "SLC":
                        cdse_product_type = "SLC"
                        sensormode = "IW"
                    elif (
                        product_type.upper() == "GRDH" or product_type.upper() == "GRD"
                    ):
                        cdse_product_type = "GRD"
                        sensormode = "IW"
                    else:
                        cdse_product_type = None
                        sensormode = "IW"

                    records.append(
                        {
                            "start_datetime": start_date,
                            "end_datetime": end_date,
                            "collection": "SENTINEL-1",
                            "name": safe_name,  # exact name pattern
                            "sensormode": sensormode,
                            "producttype": cdse_product_type,  # Set product type explicitly
                            "geometry": box(-180, -90, 180, 90),
                        }
                    )
                except Exception as e:
                    logger.warning(f"Could not parse SAFE name {safe_name}: {e}")
                    continue

            if not records:
                continue

            gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")
            # Add required id_query column if missing
            if "id_query" not in gdf.columns:
                gdf["id_query"] = [f"batch_{i}_{j}" for j in range(len(gdf))]

            try:
                # Pass cache_dir to fetch_data if configured
                with open(os.devnull, 'w') as devnull:
                    with contextlib.redirect_stdout(devnull):
                        result_df = fetch_data(
                            gdf=gdf,
                            timedelta_slice=datetime.timedelta(days=1),
                            top=1000,
                            querymode="multi",
                            cache_dir=(
                                str(cache_dir) if cache_dir else None
                            ),  # <-- Added cache_dir support
                            display_tqdm=False,
                        )
                if result_df is not None and not result_df.empty:
                    all_results.append(result_df)
                    logger.info(
                        f"Retrieved {len(result_df)} products from CDSE for this batch."
                    )
                else:
                    logger.warning(f"No products found in CDSE for batch.")
            except Exception as e:
                logger.error(f"Error querying CDSE for batch: {e}")
                import traceback

                logger.debug(traceback.format_exc())
                continue

        if not all_results:
            logger.warning("No results returned from CDSE.")
            return df

        # Combine results
        combined_results = pd.concat(all_results, ignore_index=True)
        logger.info(f"Total retrieved {len(combined_results)} products from CDSE.")

        # Create lookup dictionaries
        polygon_dict = {}
        s3path_dict = {}

        for _, row in combined_results.iterrows():
            safe_name = row.get("Name")
            if safe_name:
                if "geometry" in row and row.geometry is not None:
                    polygon_dict[safe_name] = row.geometry.wkt
                s3_path = (
                    row.get("S3path from CDSE")
                    or row.get("DownloadUrl")
                    or row.get("S3Path")
                )
                if s3_path:
                    s3path_dict[safe_name] = s3_path

        logger.info(
            f"Got polygons for {len(polygon_dict)} products and S3 paths for {len(s3path_dict)} products."
        )

        # Log which products were found vs missing
        found_slc = [name for name in missing_slc if name in polygon_dict]
        found_grd = [name for name in missing_grd if name in polygon_dict]
        missing_slc_after = [name for name in missing_slc if name not in polygon_dict]
        missing_grd_after = [name for name in missing_grd if name not in polygon_dict]

        if missing_slc_after:
            logger.warning(f"SLC products still missing polygons: {missing_slc_after}")
        if missing_grd_after:
            logger.warning(f"GRD products still missing polygons: {missing_grd_after}")

        # Update the DataFrame only for products that were missing
        # Update polygon SLC
        df = df.with_columns(
            pl.when(pl.col("SAFE SLC").is_not_null() & pl.col("polygon SLC").is_null())
            .then(
                pl.struct(["SAFE SLC"]).map_elements(
                    lambda x: (
                        polygon_dict.get(x["SAFE SLC"]) if x["SAFE SLC"] else None
                    ),
                    return_dtype=pl.Utf8,
                )
            )
            .otherwise(pl.col("polygon SLC"))
            .alias("polygon SLC")
        )

        # Update polygon GRD
        df = df.with_columns(
            pl.when(pl.col("SAFE GRD").is_not_null() & pl.col("polygon GRD").is_null())
            .then(
                pl.struct(["SAFE GRD"]).map_elements(
                    lambda x: (
                        polygon_dict.get(x["SAFE GRD"]) if x["SAFE GRD"] else None
                    ),
                    return_dtype=pl.Utf8,
                )
            )
            .otherwise(pl.col("polygon GRD"))
            .alias("polygon GRD")
        )

        # Update S3path SLC
        df = df.with_columns(
            pl.when(pl.col("SAFE SLC").is_not_null() & pl.col("S3path SLC").is_null())
            .then(
                pl.struct(["SAFE SLC"]).map_elements(
                    lambda x: s3path_dict.get(x["SAFE SLC"]) if x["SAFE SLC"] else None,
                    return_dtype=pl.Utf8,
                )
            )
            .otherwise(pl.col("S3path SLC"))
            .alias("S3path SLC")
        )

        # Update S3path GRD
        df = df.with_columns(
            pl.when(pl.col("SAFE GRD").is_not_null() & pl.col("S3path GRD").is_null())
            .then(
                pl.struct(["SAFE GRD"]).map_elements(
                    lambda x: s3path_dict.get(x["SAFE GRD"]) if x["SAFE GRD"] else None,
                    return_dtype=pl.Utf8,
                )
            )
            .otherwise(pl.col("S3path GRD"))
            .alias("S3path GRD")
        )

        # Count how many were updated
        updated_polygon_slc = df.filter(
            pl.col("SAFE SLC").is_not_null() & pl.col("polygon SLC").is_not_null()
        ).height
        updated_polygon_grd = df.filter(
            pl.col("SAFE GRD").is_not_null() & pl.col("polygon GRD").is_not_null()
        ).height
        updated_s3_slc = df.filter(
            pl.col("SAFE SLC").is_not_null() & pl.col("S3path SLC").is_not_null()
        ).height
        updated_s3_grd = df.filter(
            pl.col("SAFE GRD").is_not_null() & pl.col("S3path GRD").is_not_null()
        ).height

        logger.info(
            f"Updated polygons for {updated_polygon_slc} SLC and {updated_polygon_grd} GRD products."
        )
        logger.info(
            f"Updated S3 paths for {updated_s3_slc} SLC and {updated_s3_grd} GRD products."
        )

        return df

    def _get_checkpoint_dir(self) -> Path | None:
        """Return a checkpoint directory path based on the catalogue output path."""
        catalogue_path = self.config.get("paths", {}).get("output", {}).get("catalogue")
        if not catalogue_path:
            return None
        base_dir = Path(catalogue_path).parent
        checkpoint_dir = base_dir / "checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        return checkpoint_dir
    
    # ---------- Placeholders for future implementation ----------
    def _update_presence_columns(
        self, df: pl.DataFrame, force: bool = False
    ) -> pl.DataFrame:
        """
        Update presence columns by checking if SLC, GRD, and OCN products exist on Ifremer storage.
        Uses s1ifr.get_path_from_base_safe to check existence across all configured archives.
        """
        logger.info("Checking presence of products on Ifremer storage...")

        try:
            from s1ifr.get_path_from_base_safe import get_path_from_base_safe
        except ImportError as e:
            logger.warning(f"s1ifr not installed: {e}. Skipping presence check.")
            return df

        # Get s1ifr config file path from the main config
        s1ifr_config_path = self.config.get("s1ifr-config-file", None)
        if s1ifr_config_path:
            logger.info(f"Using s1ifr config file: {s1ifr_config_path}")

        # Determine which archives to check
        archive_names = ["datawork", "scale"]  # default fallback

        if s1ifr_config_path:
            try:
                import yaml

                with open(s1ifr_config_path) as f:
                    s1ifr_config = yaml.safe_load(f)
                if "paths" in s1ifr_config:
                    potential_archives = ["datawork", "scale"]
                    for key in s1ifr_config["paths"].keys():

                        if key not in potential_archives and isinstance(
                            s1ifr_config["paths"][key], dict
                        ):
                            # Check if this looks like an archive (has archive_esa or similar)
                            if any(
                                "archive" in k.lower()
                                for k in s1ifr_config["paths"][key].keys()
                            ):


                                potential_archives.append(key)
                    archive_names = potential_archives
                    logger.info(f"Found archives in s1ifr config: {archive_names}")
            except Exception as e:
                logger.warning(
                    f"Could not read s1ifr config to get archives: {e}. Using defaults."
                )

        # Get rows that need presence information
        if force:
            slc_rows = df.filter(pl.col("SAFE SLC").is_not_null())
            grd_rows = df.filter(pl.col("SAFE GRD").is_not_null())
            ocn_rows = df.filter(pl.col("SAFE OCN").is_not_null())  # <-- ADDED
        else:
            slc_rows = df.filter(
                pl.col("SAFE SLC").is_not_null() & pl.col("presence SLC").is_null()
            )
            grd_rows = df.filter(
                pl.col("SAFE GRD").is_not_null() & pl.col("presence GRD").is_null()
            )

            ocn_rows = df.filter(  # <-- ADDED
                pl.col("SAFE OCN").is_not_null() & pl.col("presence OCN").is_null()
            )
        
        logger.info(f"Checking presence for {slc_rows.height} SLC, {grd_rows.height} GRD, and {ocn_rows.height} OCN products.")
        
        def find_product_path(safe_name: str, product_type: str) -> Optional[str]:
            """Find product path by checking all archives sequentially."""
            for archive_name in archive_names:
                try:
                    path = get_path_from_base_safe(
                        safe_basename=safe_name,
                        archive_name=archive_name,
                        check_existence=True,
                        config_path=s1ifr_config_path,
                    )
                    if path:
                        logger.debug(
                            f"{product_type} found in {archive_name}: {safe_name} -> {path}"
                        )
                        return path  # type: ignore[no-any-return]
                except Exception as e:
                    logger.debug(f"Error checking {archive_name} for {safe_name}: {e}")
                    continue
            logger.debug(f"{product_type} not found in any archive: {safe_name}")
            return None

        # Check SLC products
        slc_presence = {}
        for row in slc_rows.to_dicts():
            safe_name = row["SAFE SLC"]
            slc_presence[safe_name] = find_product_path(safe_name, "SLC")

        # Check GRD products
        grd_presence = {}
        for row in grd_rows.to_dicts():
            safe_name = row["SAFE GRD"]
            grd_presence[safe_name] = find_product_path(safe_name, "GRD")
        
        # Check OCN products  # <-- ADDED
        ocn_presence = {}
        for row in ocn_rows.to_dicts():
            safe_name = row["SAFE OCN"]
            ocn_presence[safe_name] = find_product_path(safe_name, "OCN")
        
        # Update SLC presence column
        df = df.with_columns(
            pl.when(
                pl.col("SAFE SLC").is_not_null()
                & (pl.col("presence SLC").is_null() | pl.lit(force))
            )
            .then(
                pl.struct(["SAFE SLC"]).map_elements(
                    lambda x: (
                        slc_presence.get(x["SAFE SLC"]) if x["SAFE SLC"] else None
                    ),
                    return_dtype=pl.Utf8,
                )
            )
            .otherwise(pl.col("presence SLC"))
            .alias("presence SLC")
        )

        # Update GRD presence column
        df = df.with_columns(
            pl.when(
                pl.col("SAFE GRD").is_not_null()
                & (pl.col("presence GRD").is_null() | pl.lit(force))
            )
            .then(
                pl.struct(["SAFE GRD"]).map_elements(
                    lambda x: (
                        grd_presence.get(x["SAFE GRD"]) if x["SAFE GRD"] else None
                    ),
                    return_dtype=pl.Utf8,
                )
            )
            .otherwise(pl.col("presence GRD"))
            .alias("presence GRD")
        )
        
        # Update OCN presence column  # <-- ADDED
        df = df.with_columns(
            pl.when(
                pl.col("SAFE OCN").is_not_null() & 
                (pl.col("presence OCN").is_null() | pl.lit(force))
            )
            .then(
                pl.struct(["SAFE OCN"])
                .map_elements(
                    lambda x: ocn_presence.get(x["SAFE OCN"]) if x["SAFE OCN"] else None,
                    return_dtype=pl.Utf8
                )
            )
            .otherwise(pl.col("presence OCN"))
            .alias("presence OCN")
        )
        
        # Count how many were found
        found_slc = df.filter(pl.col("SAFE SLC").is_not_null() & pl.col("presence SLC").is_not_null()).height
        found_grd = df.filter(pl.col("SAFE GRD").is_not_null() & pl.col("presence GRD").is_not_null()).height
        found_ocn = df.filter(pl.col("SAFE OCN").is_not_null() & pl.col("presence OCN").is_not_null()).height  # <-- ADDED
        
        total_slc = df.filter(pl.col("SAFE SLC").is_not_null()).height
        total_grd = df.filter(pl.col("SAFE GRD").is_not_null()).height
        total_ocn = df.filter(pl.col("SAFE OCN").is_not_null()).height  # <-- ADDED
        
        if total_slc > 0:
            logger.info(
                f"Found {found_slc}/{total_slc} SLC products on Ifremer storage ({found_slc/total_slc*100:.1f}%)"
            )
        if total_grd > 0:
            logger.info(f"Found {found_grd}/{total_grd} GRD products on Ifremer storage ({found_grd/total_grd*100:.1f}%)")
        if total_ocn > 0:  # <-- ADDED
            logger.info(f"Found {found_ocn}/{total_ocn} OCN products on Ifremer storage ({found_ocn/total_ocn*100:.1f}%)")
        
        return df

    def _update_derived_products(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Update derived product columns (L1B, L1C, L2WAV) using s1ifr.get_products_family.

        Uses batch processing to efficiently check all SLCs at once.
        """
        logger.info("Checking derived products (L1B, L1C, L2WAV)...")

        try:
            import pandas as pd
            from s1ifr.paths_safe_product_family import get_products_family
        except ImportError as e:
            logger.warning(
                f"s1ifr or pandas not installed: {e}. Skipping derived product check."
            )
            return df

        # Get s1ifr config file path from the main config
        s1ifr_config_path = self.config.get("s1ifr-config-file", None)
        if s1ifr_config_path:
            logger.info(f"Using s1ifr config file: {s1ifr_config_path}")

        # Get product versions from config or use defaults
        product_versions = self.config.get("product_versions", {})
        l1b_versions = product_versions.get("l1b", ["A21", "A23"])
        l1c_versions = product_versions.get("l1c", ["B17", "B21"])
        # L2WAV versions are handled by s1ifr defaults if not specified

        logger.info(f"L1B versions to check: {l1b_versions}")
        logger.info(f"L1C versions to check: {l1c_versions}")

        # Get SLCs that need checking
        # Check if any derived product column is NULL for this SLC
        slc_rows = df.filter(pl.col("SAFE SLC").is_not_null())

        if slc_rows.height == 0:
            logger.info("No SLC products found to check for derived products.")
            return df

        # Build list of columns to check
        derived_cols = []
        for v in l1b_versions:
            derived_cols.append(f"presence L1B XSP {v}")
        for v in l1c_versions:
            derived_cols.append(f"presence L1C XSP {v}")
        derived_cols.extend(["presence L2 WAV E11", "presence L2 WAV E13"])

        # Only process SLCs that are missing at least one derived product
        # Build condition: any derived column is NULL
        condition = None
        for col in derived_cols:
            if col in df.columns:
                cond = pl.col(col).is_null()
                condition = cond if condition is None else condition | cond

        if condition is not None:
            slc_rows = slc_rows.filter(condition)
        else:
            # If none of the derived columns exist, check all SLCs
            pass

        if slc_rows.height == 0:
            logger.info("All SLCs already have derived product information.")
            return df

        logger.info(f"Checking derived products for {slc_rows.height} SLC products.")

        # Prepare pandas DataFrame for s1ifr
        slc_list = slc_rows["SAFE SLC"].to_list()
        pd_df = pd.DataFrame({"L1_SLC": slc_list})

        try:
            # Call get_products_family
            result_df = get_products_family(
                pd_df,
                l1bversions=l1b_versions,
                l1cversions=l1c_versions,
                config=s1ifr_config_path,
                disable_tqdm=True,
            )
            logger.info(f"Processed {len(result_df)} SLCs with get_products_family.")
        except Exception as e:
            logger.error(f"Error calling get_products_family: {e}")
            import traceback

            logger.debug(traceback.format_exc())
            return df

        # Build lookup dictionaries for each product column
        lookup_dicts = {}
        for col in result_df.columns:
            if col != "L1_SLC":
                lookup_dicts[col] = dict(zip(result_df["L1_SLC"], result_df[col]))

        logger.info(f"Found derived products: {list(lookup_dicts.keys())}")

        # Map s1ifr column names to catalogue column names
        col_mapping = {}
        for v in l1b_versions:
            col_mapping[f"L1B_XSP_{v}"] = f"presence L1B XSP {v}"
        for v in l1c_versions:
            col_mapping[f"L1C_XSP_{v}"] = f"presence L1C XSP {v}"
        col_mapping["L2_WAV_E11"] = "presence L2 WAV E11"
        col_mapping["L2_WAV_E13"] = "presence L2 WAV E13"

        # Update the DataFrame for each derived product column
        for src_col, dst_col in col_mapping.items():
            if src_col in lookup_dicts:
                mapping = lookup_dicts[src_col]
                # Update only rows that were missing this information
                df = df.with_columns(
                    pl.when(
                        pl.col("SAFE SLC").is_not_null()
                        & (pl.col(dst_col).is_null() if dst_col in df.columns else True)
                    )
                    .then(
                        pl.struct(["SAFE SLC"]).map_elements(
                            lambda x: (
                                mapping.get(x["SAFE SLC"], None)
                                if x["SAFE SLC"]
                                else None
                            ),
                            return_dtype=pl.Utf8,
                        )
                    )
                    .otherwise(pl.col(dst_col) if dst_col in df.columns else None)
                    .alias(dst_col)
                )
                updated_count = df.filter(
                    pl.col("SAFE SLC").is_not_null() & pl.col(dst_col).is_not_null()
                ).height
                logger.info(f"  {dst_col}: found {updated_count} products")

        return df

    def _link_ocn_to_grd(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Link OCN products to GRD products using CDSE.
        Uses the GRD footprint for spatial filtering when available.
        """
        logger.info("Linking OCN to GRD products...")
        
        # Find GRD rows without OCN
        grd_without_ocn = df.filter(
            pl.col("SAFE GRD").is_not_null() &
            pl.col("SAFE OCN").is_null() &
            (pl.col("presence OCN").is_null() | (pl.col("presence OCN") != "NOT_FOUND"))
        )
        
        if grd_without_ocn.height == 0:
            logger.info("All GRD products already have OCN linked.")
            return df
        
        logger.info(f"Attempting to link OCN for {grd_without_ocn.height} GRD products...")
        
        updates = {}
        for row in grd_without_ocn.to_dicts():
            grd_name = row["SAFE GRD"]
            grd_polygon = row.get("polygon GRD")
            
            try:
                # Use CDSE to find OCN for this GRD
                ocn_name = self._call_cdse_get_ocn_from_grd(grd_name, grd_polygon)
                if ocn_name:
                    updates[grd_name] = ocn_name
                    logger.debug(f"CDSE found OCN for GRD {grd_name} -> {ocn_name}")
                else:
                    # Mark as not found
                    df = df.with_columns(
                        pl.when(pl.col("SAFE GRD") == grd_name)
                        .then(pl.lit("NOT_FOUND"))
                        .otherwise(pl.col("presence OCN"))
                        .alias("presence OCN")
                    )
                    logger.warning(f"CDSE could not find OCN for GRD {grd_name}")
            except Exception as e:
                logger.error(f"Error linking OCN for GRD {grd_name}: {e}")
        
        # Apply updates
        for grd_name, ocn_name in updates.items():
            df = df.with_columns(
                pl.when(pl.col("SAFE GRD") == grd_name)
                .then(pl.lit(ocn_name))
                .otherwise(pl.col("SAFE OCN"))
                .alias("SAFE OCN")
            )
        
        logger.info(f"Linked OCN to {len(updates)} GRD products.")
        return df

    def _link_ocn_to_slc(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Fallback: Link OCN to SLC products when GRD link failed.
        """
        logger.info("Fallback: Linking OCN to SLC products...")
        
        # Find SLC rows without OCN
        slc_without_ocn = df.filter(
            pl.col("SAFE SLC").is_not_null() &
            pl.col("SAFE GRD").is_null() &          # <-- Only SLC-only rows
            pl.col("SAFE OCN").is_null() &
            (pl.col("presence OCN").is_null() | (pl.col("presence OCN") != "NOT_FOUND"))
        )
        
        if slc_without_ocn.height == 0:
            logger.info("No SLC products need OCN fallback linking.")
            return df
        
        logger.info(f"Attempting to link OCN for {slc_without_ocn.height} SLC products...")
        
        # Get list of SLCs that already have OCN via GRD
        # Use a different approach: collect the data first
        linked_via_grd_names = set()
        for row in df.filter(
            pl.col("SAFE GRD").is_not_null() & 
            pl.col("SAFE OCN").is_not_null()
        ).to_dicts():
            linked_via_grd_names.add(row.get("SAFE SLC"))
        
        updates = {}
        for row in slc_without_ocn.to_dicts():
            slc_name = row["SAFE SLC"]
            
            # Skip if this SLC already has a GRD with OCN
            if slc_name in linked_via_grd_names:
                continue
            
            slc_polygon = row.get("polygon SLC")
            
            try:
                ocn_name = self._call_cdse_get_ocn_from_slc(slc_name, slc_polygon)
                if ocn_name:
                    updates[slc_name] = ocn_name
                    logger.debug(f"CDSE found OCN for SLC {slc_name} -> {ocn_name}")
                else:
                    logger.warning(f"CDSE could not find OCN for SLC {slc_name}")
            except Exception as e:
                logger.error(f"Error linking OCN for SLC {slc_name}: {e}")
        
        # Apply updates
        for slc_name, ocn_name in updates.items():
            df = df.with_columns(
                pl.when(pl.col("SAFE SLC") == slc_name)
                .then(pl.lit(ocn_name))
                .otherwise(pl.col("SAFE OCN"))
                .alias("SAFE OCN")
            )
        
        logger.info(f"Linked OCN to {len(updates)} SLC products.")
        return df

    

    def _call_cdse_get_ocn_from_grd(self, grd_name: str, polygon_wkt: Optional[str] = None) -> Optional[str]:
        """
        Query CDSE to find OCN for a given GRD.
        Uses polygon for spatial filtering if available.
        """
        try:
            from cdsodatacli.scripts.match_s1_product_types import find_product_for_safe
        except ImportError:
            logger.warning("cdsodatacli not installed")
            return None
        
        target_type = "OCN_"
        delta_dist = defaultdict(int)
        
        try:
            result = find_product_for_safe(
                source_id=grd_name,
                target_type=target_type,
                logger=logger,
                delta_distribution=delta_dist
            )
            if result and "target_name" in result:
                return result["target_name"]
        except Exception as e:
            logger.error(f"CDSE query failed for {grd_name}: {e}")
        
        return None


    def _call_cdse_get_ocn_from_slc(self, slc_name: str, polygon_wkt: Optional[str] = None) -> Optional[str]:
        """
        Query CDSE to find OCN for a given SLC.
        Uses polygon for spatial filtering if available.
        """
        try:
            from cdsodatacli.scripts.match_s1_product_types import find_product_for_safe
        except ImportError:
            logger.warning("cdsodatacli not installed")
            return None
        
        target_type = "OCN_"
        delta_dist = defaultdict(int)
        
        try:
            result = find_product_for_safe(
                source_id=slc_name,
                target_type=target_type,
                logger=logger,
                delta_distribution=delta_dist
            )
            if result and "target_name" in result:
                return result["target_name"]
        except Exception as e:
            logger.error(f"CDSE query failed for {slc_name}: {e}")
        
        return None
    
    def merge_catalogues(
        self,
        catalogue_paths: list[Path | str],
        output_path: Path | str,
        config_path: Path | str | None = None,
        ) -> None:
        """
        Merge multiple catalogues into a single Parquet file.

        - Each row is identified by its SAFE SLC/GRD/OCN (only one non-null).
        - For duplicates, dataset lists are unioned, category is chosen by priority,
        horodating takes the most recent, and presence columns keep first non-null.
        """
        import polars as pl
        from pathlib import Path

        # Convert all inputs to Path objects
        catalogue_paths = [Path(p) for p in catalogue_paths]
        output_path = Path(output_path)
        if config_path:
            config_path = Path(config_path)

        if len(catalogue_paths) < 2:
            raise ValueError("At least two catalogues are required for merging.")

        # Validate schemas
        schemas = []
        for p in catalogue_paths:
            if not p.exists():
                raise FileNotFoundError(f"Catalogue not found: {p}")
            # Read only the schema (no data) to compare
            df = pl.read_parquet(p, n_rows=0)
            schemas.append(df.schema)

        # Ensure all schemas are identical
        base_schema = schemas[0]
        for i, s in enumerate(schemas[1:], start=1):
            if s != base_schema:
                raise ValueError(f"Schema mismatch in {catalogue_paths[i]}. Expected {base_schema}, got {s}")



        # Read all catalogues into a single DataFrame (lazy scanning could be used for large files)
        # We'll use pl.scan_parquet for memory efficiency, then collect after grouping.
        lazy_dfs = [pl.scan_parquet(str(p)) for p in catalogue_paths]
        combined = pl.concat(lazy_dfs, how="vertical_relaxed")

        # Create unique identifier: SAFE SLC if not null, else SAFE GRD, else SAFE OCN
        combined = combined.with_columns(
            pl.when(pl.col("SAFE SLC").is_not_null())
            .then(pl.col("SAFE SLC"))
            .when(pl.col("SAFE GRD").is_not_null())
            .then(pl.col("SAFE GRD"))
            .otherwise(pl.col("SAFE OCN"))
            .alias("_safe_id")
        )

        # Sort by horodating descending so that the most recent row is first per group
        combined = combined.sort("horodating", descending=True)

        # Group by _safe_id and aggregate
        # For columns that should be merged, we use:
        # - first (since sorted, first is the most recent horodating)
        # - concat_list + unique for dataset(s)
        # - custom max for category via a map
        aggregated = combined.group_by("_safe_id").agg([
            # Primary SAFE columns: take first (most recent row)
            pl.col("SAFE SLC").first().alias("SAFE SLC"),
            pl.col("SAFE GRD").first().alias("SAFE GRD"),
            pl.col("SAFE OCN").first().alias("SAFE OCN"),

            # Dataset list: union of all
            pl.concat_list("dataset(s) d'appartenance")
            .list.unique()
            .alias("dataset(s) d'appartenance"),

            # Dataset category: highest priority (undefined < train < val < test)
            # We'll use a custom aggregation with a helper function
            # But we can use a map_elements on the list of categories
            # Since we don't have a direct aggregation for category priority, we'll do it after grouping.
            # We'll first collect all categories per group, then compute the priority later.
            pl.col("dataset_category").alias("_categories"),

            # Presence columns: take first (most recent horodating)
            pl.col("presence SLC").first().alias("presence SLC"),
            pl.col("presence GRD").first().alias("presence GRD"),
            pl.col("presence OCN").first().alias("presence OCN"),
            pl.col("presence L1B XSP A21").first().alias("presence L1B XSP A21"),
            pl.col("presence L1C XSP B17").first().alias("presence L1C XSP B17"),

            # Meteorological and other columns: take first
            pl.col("Hs WW3").first().alias("Hs WW3"),
            pl.col("Tp WW3").first().alias("Tp WW3"),
            pl.col("U10 ecmwf").first().alias("U10 ecmwf"),
            pl.col("v10 ecmwf").first().alias("v10 ecmwf"),
            pl.col("start date SAFE").first().alias("start date SAFE"),
            pl.col("horodating").first().alias("horodating"),  # we already sorted by horodating, so first is max
            pl.col("polygon SLC").first().alias("polygon SLC"),
            pl.col("polygon GRD").first().alias("polygon GRD"),
            pl.col("S3path SLC").first().alias("S3path SLC"),
            pl.col("S3path GRD").first().alias("S3path GRD"),
            pl.col("polarization").first().alias("polarization"),
            pl.col("unité").first().alias("unité"),
        ])

        # Now compute the category using priority logic from _compute_category_and_conflicts
        # We need to apply the same priority function to each group's categories.
        # We can use map_elements on the "_categories" list column.
        # First, we need to re-import the priority function (or duplicate it).
        # We'll define a small function inside this method.
        def _category_priority(category: str) -> int:
            priorities = {"undefined": 0, "train": 1, "val": 2, "test": 3}
            return priorities.get(category.lower(), 0)

        def _best_category(categories: list[str]) -> str:
            if not categories:
                return "undefined"
            # Remove None and empty strings
            categories = [c for c in categories if c]
            if not categories:
                return "undefined"
            # Pick category with highest priority
            return max(categories, key=_category_priority)

        # Apply the function to the "_categories" column
        aggregated = aggregated.with_columns(
            pl.struct(["_categories"])
            .map_elements(lambda x: _best_category(x["_categories"]), return_dtype=pl.Utf8)
            .alias("dataset_category")
        )

        # Drop the temporary _categories column
        aggregated = aggregated.drop("_categories", "_safe_id")

        # Ensure the columns are in the correct order (same as SCHEMA)
        # Convert to a DataFrame and select columns in SCHEMA order
        merged_df = aggregated.select(list(SCHEMA.keys()))

        # Write to output with metadata (using existing helper)
        # We need a way to write with metadata; since we are in updater, we can call a method from catalogue or handle it here.
        # We'll write using polars directly, and later the caller can add metadata if needed.
        # merged_df.write_parquet(output_path, compression="snappy")
        merged_df.sink_parquet(output_path, compression="snappy")
        logger.info(f"Merged catalogue written to {output_path}")

    def update_meteorology(self, df: pl.DataFrame, force: bool = False) -> pl.DataFrame:
        return df

    def _get_safe_centroid(self, polygon_wkt: str) -> tuple[float, float]:
        return (0.0, 0.0)

    def _call_cdse_match(self, safe_name: str) -> list[str]:
        return []
