"""Incremental update logic for the catalogue."""

from typing import Any, Dict, List, Optional, Tuple

import datetime
import logging
import re
import time
from collections import defaultdict
from pathlib import Path

import polars as pl

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
        slc_listings: str | Path | list[str] | dict[str, Any],
        grd_listings: str | Path | list[str] | dict[str, Any],
    ) -> pl.DataFrame:
        """
        Combine SLC and GRD listings into a catalogue DataFrame (no external queries).

        Now handles dataset names from the configuration structure:
        paths:
        reference_listings:
            slc:
            "hibou2": "assets/listings/dummy_slc_listing_hibou.txt"
            "castor5": "assets/listings/dummy_slc_listing_castor.txt"
            grd:
            "zebra": "assets/listings/dummy_grd_listing_zebre.txt"
        """
        logger.info("Building catalogue from SLC listings...")

        # Handle both old format (list) and new format (dict with dataset names)
        slc_dfs = []
        if isinstance(slc_listings, dict):
            # New format: dataset_name -> listing_path
            for dataset_name, listing_path in slc_listings.items():
                logger.info(f"Reading SLC dataset '{dataset_name}' from {listing_path}")
                df_raw = self.read_listings(listing_path)
                if df_raw.height > 0:
                    # Add dataset name to each row
                    df_raw = df_raw.with_columns(
                        pl.lit([dataset_name], dtype=pl.List(pl.Utf8)).alias(
                            "dataset(s) d'appartenance"
                        )
                    )
                    slc_dfs.append(df_raw)
                else:
                    logger.warning(
                        f"No valid SLC entries found in dataset '{dataset_name}'"
                    )
        else:
            # Old format: single path or list of paths (no dataset names)
            df_raw = self.read_listings(slc_listings)
            if df_raw.height > 0:
                df_raw = df_raw.with_columns(
                    pl.lit([], dtype=pl.List(pl.Utf8)).alias(
                        "dataset(s) d'appartenance"
                    )
                )
                slc_dfs.append(df_raw)

        if not slc_dfs:
            logger.warning("No valid SLC entries found. The SLC part will be empty.")
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

        # Build SLC rows
        slc_df = slc_df_raw.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("SAFE GRD"),
            pl.lit(None, dtype=pl.Utf8).alias("SAFE OCN"),
            pl.col("safe_name").alias("SAFE SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("presence SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("presence GRD"),
            pl.lit(None, dtype=pl.Utf8).alias("presence OCN"),
            pl.lit(None, dtype=pl.Utf8).alias("presence L1B XSP A21"),
            pl.lit(None, dtype=pl.Utf8).alias("presence L1C XSP B17"),
            # dataset(s) d'appartenance already has the dataset name(s)
            pl.lit(None, dtype=pl.Float32).alias("Hs WW3"),  # <-- ADD THIS
            pl.lit(None, dtype=pl.Float32).alias("Tp WW3"),  # <-- ADD THIS
            pl.lit(None, dtype=pl.Float32).alias("U10 ecmwf"),  # <-- ADD THIS
            pl.lit(None, dtype=pl.Float32).alias("v10 ecmwf"),  # <-- ADD THIS
            pl.col("start_date").alias("start date SAFE"),
            pl.lit(datetime.datetime.now()).alias("horodating"),
            pl.lit(None, dtype=pl.Utf8).alias("polygon SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("polygon GRD"),
            pl.lit(None, dtype=pl.Utf8).alias("S3path SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("S3path GRD"),
            pl.col("polarization").alias("polarization"),
            pl.col("mission").alias("unité"),
        ).select(list(SCHEMA.keys()))

        # GRD listings
        logger.info("Building catalogue from GRD listings...")

        grd_dfs = []
        if isinstance(grd_listings, dict):
            for dataset_name, listing_path in grd_listings.items():
                logger.info(f"Reading GRD dataset '{dataset_name}' from {listing_path}")
                df_raw = self.read_listings(listing_path)
                if df_raw.height > 0:
                    df_raw = df_raw.with_columns(
                        pl.lit([dataset_name], dtype=pl.List(pl.Utf8)).alias(
                            "dataset(s) d'appartenance"
                        )
                    )
                    grd_dfs.append(df_raw)
                else:
                    logger.warning(
                        f"No valid GRD entries found in dataset '{dataset_name}'"
                    )
        else:
            df_raw = self.read_listings(grd_listings)
            if df_raw.height > 0:
                df_raw = df_raw.with_columns(
                    pl.lit([], dtype=pl.List(pl.Utf8)).alias(
                        "dataset(s) d'appartenance"
                    )
                )
                grd_dfs.append(df_raw)

        if not grd_dfs:
            logger.warning("No valid GRD entries found. The GRD part will be empty.")
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

        # Build GRD rows
        grd_df = grd_df_raw.with_columns(
            pl.col("safe_name").alias("SAFE GRD"),
            pl.lit(None, dtype=pl.Utf8).alias("SAFE SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("SAFE OCN"),
            pl.lit(None, dtype=pl.Utf8).alias("presence SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("presence GRD"),
            pl.lit(None, dtype=pl.Utf8).alias("presence OCN"),
            pl.lit(None, dtype=pl.Utf8).alias("presence L1B XSP A21"),
            pl.lit(None, dtype=pl.Utf8).alias("presence L1C XSP B17"),
            pl.lit(None, dtype=pl.Float32).alias("Hs WW3"),  # <-- ADD THIS
            pl.lit(None, dtype=pl.Float32).alias("Tp WW3"),  # <-- ADD THIS
            pl.lit(None, dtype=pl.Float32).alias("U10 ecmwf"),  # <-- ADD THIS
            pl.lit(None, dtype=pl.Float32).alias("v10 ecmwf"),  # <-- ADD THIS
            pl.col("start_date").alias("start date SAFE"),
            pl.lit(datetime.datetime.now()).alias("horodating"),
            pl.lit(None, dtype=pl.Utf8).alias("polygon SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("polygon GRD"),
            pl.lit(None, dtype=pl.Utf8).alias("S3path SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("S3path GRD"),
            pl.col("polarization").alias("polarization"),
            pl.col("mission").alias("unité"),
        ).select(list(SCHEMA.keys()))

        # Combine SLC and GRD
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
        Link SLC and GRD products using multi-step strategy:
        1. Local matching based on naming conventions and time window search
        2. CDSE fallback for orphans (using cdsodatacli)
        3. Fetch polygons and S3 paths from CDSE
        4. Check presence on Ifremer storage using s1ifr
        5. Check derived products (L1B, L1C, L2WAV) using s1ifr.paths_safe_product_family
        """
        logger.info("=" * 60)
        logger.info("🚀 Starting SLC-GRD linking pipeline...")
        logger.info("=" * 60)
        start_total = time.time()

        # Step 1: Local matching
        logger.info("\n📍 Step 1/5: Local SLC-GRD matching...")
        start = time.time()
        df = self._local_link_slc_grd(df)
        elapsed = time.time() - start
        self._log_catalogue_summary(df, "After local matching")
        logger.info(f"✅ Step 1/5 completed in {elapsed:.1f}s")

        # Step 2: CDSE fallback for rows still missing links
        logger.info("\n📍 Step 2/5: CDSE fallback for orphan products...")
        start = time.time()
        df = self._cdse_fallback_link(df)
        df = self._merge_linked_rows(df)
        elapsed = time.time() - start
        self._log_catalogue_summary(df, "After CDSE fallback")
        logger.info(f"✅ Step 2/5 completed in {elapsed:.1f}s")

        # Step 3: Fetch polygons and S3 paths from CDSE
        logger.info("\n📍 Step 3/5: Fetching polygons and S3 paths from CDSE...")
        start = time.time()
        df = self._update_polygons_and_s3paths(df)
        elapsed = time.time() - start
        self._log_catalogue_summary(df, "After polygon fetch")
        logger.info(f"✅ Step 3/5 completed in {elapsed:.1f}s")

        # Step 4: Check presence on Ifremer storage
        logger.info("\n📍 Step 4/5: Checking presence on Ifremer storage...")
        start = time.time()
        df = self._update_presence_columns(df, force=False)
        elapsed = time.time() - start
        self._log_catalogue_summary(df, "After presence check")
        logger.info(f"✅ Step 4/5 completed in {elapsed:.1f}s")

        # Step 5: Check derived products (L1B, L1C, L2WAV)
        logger.info("\n📍 Step 5/5: Checking derived products (L1B, L1C, L2WAV)...")
        start = time.time()
        df = self._update_derived_products(df)
        elapsed = time.time() - start
        self._log_catalogue_summary(df, "After derived products")
        logger.info(f"✅ Step 5/5 completed in {elapsed:.1f}s")

        total_elapsed = time.time() - start_total
        logger.info("=" * 60)
        logger.info(f"🏁 SLC-GRD linking complete in {total_elapsed:.1f}s")
        logger.info(f"📊 Final catalogue shape: {df.shape}")
        logger.info("=" * 60)

        return df

    def _local_link_slc_grd(self, df: pl.DataFrame) -> pl.DataFrame:
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

        def extract_start_time(safe_name: str) -> datetime.datetime:
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
                    return None  # type: ignore[return-value]
            return None  # type: ignore[return-value]

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
                    {"safe_name": row["SAFE SLC"], "start_time": start_time}
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
                slc_name = slc_info["safe_name"]
                slc_start_time = slc_info["start_time"]

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
                    first_slc = slc_dict[key][0]["safe_name"]
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
        slc_name = grd_name.replace("_GRDH_", "_SLC__").replace("_GRD_", "_SLC_")

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
        grd_name = slc_name.replace("_SLC__", "_GRDH_").replace("_SLC_", "_GRD_")

        def adjust_timestamp(match):
            dt = datetime.datetime.strptime(match.group(0), "%Y%m%dT%H%M%S")
            dt = dt + datetime.timedelta(seconds=offset_seconds)
            return dt.strftime("%Y%m%dT%H%M%S")

        grd_name = re.sub(r"\d{8}T\d{6}", adjust_timestamp, grd_name, count=1)
        return grd_name

    def _cdse_fallback_link(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        For rows still missing links, query CDSE using cdsodatacli.
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

        # Process GRD orphans
        updates_grd = {}
        for row in grd_orphans.to_dicts():
            grd_name = row["SAFE GRD"]
            try:
                slc_name = self._call_cdse_get_parent_slc(grd_name)
                if slc_name:
                    updates_grd[grd_name] = slc_name
                    logger.info(f"CDSE found parent SLC for {grd_name} -> {slc_name}")
                else:
                    logger.warning(f"CDSE could not find SLC for {grd_name}")
            except Exception as e:
                logger.error(f"CDSE error for {grd_name}: {e}")

        # Apply updates for GRD orphans (code unchanged)
        for grd_name, slc_name in updates_grd.items():
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

        # Process SLC orphans
        updates_slc = {}
        for row in slc_orphans.to_dicts():
            slc_name = row["SAFE SLC"]
            if any(grd for grd, slc in updates_grd.items() if slc == slc_name):
                continue
            try:
                grd_name = self._call_cdse_get_derived_grd(slc_name)
                if grd_name:
                    updates_slc[slc_name] = grd_name
                    logger.info(f"CDSE found derived GRD for {slc_name} -> {grd_name}")
                else:
                    logger.warning(f"CDSE could not find GRD for {slc_name}")
            except Exception as e:
                logger.error(f"CDSE error for {slc_name}: {e}")

        # Apply updates for SLC orphans (code unchanged)
        for slc_name, grd_name in updates_slc.items():
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

        total_updates = len(updates_grd) + len(updates_slc)
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
            if result and "target_name" in result:
                return result["target_name"]
            else:
                note = result.get("note", "unknown reason")
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

        target_type = "GRD_"  # Valid type for GRD
        delta_dist: defaultdict[str, int] = defaultdict(int)

        try:
            result = find_product_for_safe(
                source_id=slc_name,
                target_type=target_type,
                logger=logger,
                delta_distribution=delta_dist,
            )
            if result and "target_name" in result:
                return result["target_name"]
            else:
                note = result.get("note", "unknown reason")
                logger.warning(f"CDSE did not find GRD for {slc_name}: {note}")
                return None
        except Exception as e:
            logger.error(f"CDSE query failed for {slc_name}: {e}")
            return None

    def find_new_safe(
        self,
        existing_df: pl.DataFrame,
        slc_listing: str | Path | list[str],
        grd_listing: str | Path | list[str],
    ) -> pl.DataFrame:
        """Identify SAFE not yet present in the catalogue."""
        new_raw = self.build_from_listings(slc_listing, grd_listing)
        if existing_df.height == 0:
            return new_raw

        existing_slc = set(
            existing_df.filter(pl.col("SAFE SLC").is_not_null())["SAFE SLC"].to_list()
        )
        existing_grd = set(
            existing_df.filter(pl.col("SAFE GRD").is_not_null())["SAFE GRD"].to_list()
        )

        new_rows = []
        for row in new_raw.to_dicts():
            if row["SAFE SLC"] and row["SAFE SLC"] not in existing_slc:
                new_rows.append(row)
            elif row["SAFE GRD"] and row["SAFE GRD"] not in existing_grd:
                new_rows.append(row)

        if not new_rows:
            logger.info("No new SAFE found.")
            return pl.DataFrame(schema=SCHEMA)
        logger.info(f"Found {len(new_rows)} new SAFE entries.")
        return pl.DataFrame(new_rows, schema=SCHEMA)

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

        # For dataset merging, we need to handle empty lists carefully.
        # First, create a temporary column with all datasets concatenated
        # Then explode, get unique, and aggregate back

        # Convert the linked rows to a list of dictionaries and process manually
        # This is simpler and more reliable for this specific operation
        rows = linked_rows.to_dicts()

        merged_rows = []
        # Group by (SAFE SLC, SAFE GRD) pair
        pairs: dict[str, list[str]] = {}
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
                merged["start date SAFE"] = min(start_dates)

            # horodating: take the maximum (most recent)
            horodatings = [
                r.get("horodating")
                for r in rows_list
                if r.get("horodating") is not None
            ]
            if horodatings:
                merged["horodating"] = max(horodatings)

            # polygon SLC/GRD: take first non-null
            for poly_col in ["polygon SLC", "polygon GRD", "S3path SLC", "S3path GRD"]:
                for r in rows_list:
                    val = r.get(poly_col)
                    if val is not None:
                        merged[poly_col] = val
                        break

            # SAFE OCN is always None
            merged["SAFE OCN"] = None

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
            import shapely
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
                    mission = parsed["mission"]
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
                result_df = fetch_data(
                    gdf=gdf,
                    timedelta_slice=datetime.timedelta(days=1),
                    top=1000,
                    querymode="seq",
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

    # ---------- Placeholders for future implementation ----------
    def _update_presence_columns(
        self, df: pl.DataFrame, force: bool = False
    ) -> pl.DataFrame:
        """
        Update presence columns by checking if SLC and GRD products exist on Ifremer storage.
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
        # If we have the s1ifr config, we can read all archive names from it
        archive_names = ["datawork", "scale"]  # default fallback

        if s1ifr_config_path:
            try:
                import yaml

                with open(s1ifr_config_path) as f:
                    s1ifr_config = yaml.safe_load(f)
                # Get all top-level keys from the 'paths' section that are archive names
                if "paths" in s1ifr_config:
                    # Common archive names: datawork, scale, scratch
                    # We could also look for any key that contains 'archive' or specific archive paths
                    potential_archives = ["datawork", "scale"]
                    # Also check if there are other archive paths defined
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
        else:
            slc_rows = df.filter(
                pl.col("SAFE SLC").is_not_null() & pl.col("presence SLC").is_null()
            )
            grd_rows = df.filter(
                pl.col("SAFE GRD").is_not_null() & pl.col("presence GRD").is_null()
            )

        logger.info(
            f"Checking presence for {slc_rows.height} SLC and {grd_rows.height} GRD products."
        )

        def find_product_path(safe_name: str, product_type: str) -> str | None:
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

        # Count how many were found
        found_slc = df.filter(
            pl.col("SAFE SLC").is_not_null() & pl.col("presence SLC").is_not_null()
        ).height
        found_grd = df.filter(
            pl.col("SAFE GRD").is_not_null() & pl.col("presence GRD").is_not_null()
        ).height
        total_slc = df.filter(pl.col("SAFE SLC").is_not_null()).height
        total_grd = df.filter(pl.col("SAFE GRD").is_not_null()).height

        if total_slc > 0:
            logger.info(
                f"Found {found_slc}/{total_slc} SLC products on Ifremer storage ({found_slc/total_slc*100:.1f}%)"
            )
        if total_grd > 0:
            logger.info(
                f"Found {found_grd}/{total_grd} GRD products on Ifremer storage ({found_grd/total_grd*100:.1f}%)"
            )

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

    def update_meteorology(self, df: pl.DataFrame, force: bool = False) -> pl.DataFrame:
        return df

    def _get_safe_centroid(self, polygon_wkt: str) -> tuple[float, float]:
        return (0.0, 0.0)

    def _call_cdse_match(self, safe_name: str) -> list[str]:
        return []
