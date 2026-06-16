"""Incremental update logic for the catalogue."""

import datetime
import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple, Union
from collections import defaultdict
import polars as pl

from s1iw_catalogue.schema import SCHEMA

# Set up module-level logger
logger = logging.getLogger(__name__)


class CatalogueUpdater:
    """Handles incremental updates of the catalogue."""

    def __init__(self, config: dict) -> None:
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
    def parse_safe_name(safe_name: str) -> dict:
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
        pattern = r"^(S1[ABCD])_IW_([A-Z]+)_+([0-9A-Z]*)_(\d{8}T\d{6})_"
        match = re.match(pattern, name)
        if not match:
            raise ValueError(f"Unable to parse SAFE name: {safe_name}")

        mission = match.group(1)
        product_type = match.group(2)
        polarization = match.group(3) if match.group(3) else ""  # empty if double underscore
        start_date_str = match.group(4)
        start_date = datetime.datetime.strptime(start_date_str, "%Y%m%dT%H%M%S")

        return {
            "safe_name": safe_name,
            "mission": mission,
            "product_type": product_type,
            "polarization": polarization,
            "start_date": start_date,
        }

    def _read_one_listing(self, path: Path) -> pl.DataFrame:
        """Read a single listing file (one SAFE name per line)."""
        logger.debug(f"Reading listing file: {path}")
        if not path.exists():
            logger.warning(f"Listing file does not exist: {path}")
            return pl.DataFrame(schema={
                "safe_name": pl.Utf8,
                "mission": pl.Utf8,
                "product_type": pl.Utf8,
                "polarization": pl.Utf8,
                "start_date": pl.Datetime,
            })

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
            return pl.DataFrame(schema={
                "safe_name": pl.Utf8,
                "mission": pl.Utf8,
                "product_type": pl.Utf8,
                "polarization": pl.Utf8,
                "start_date": pl.Datetime,
            })
        logger.info(f"Successfully parsed {len(data)} entries from {path}")
        return pl.DataFrame(data)

    def read_listings(self, listing_paths: Union[Path, str, List[Union[Path, str]]]) -> pl.DataFrame:
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
            return pl.DataFrame(schema={
                "safe_name": pl.Utf8,
                "mission": pl.Utf8,
                "product_type": pl.Utf8,
                "polarization": pl.Utf8,
                "start_date": pl.Datetime,
            })

        combined = pl.concat(all_dfs, how="vertical_relaxed").unique(subset=["safe_name"])
        logger.info(f"Total unique SAFE names after combining listings: {combined.height}")
        return combined

    def build_from_listings(self,
                           slc_listings: Union[str, Path, List],
                           grd_listings: Union[str, Path, List]) -> pl.DataFrame:
        """Combine SLC and GRD listings into a catalogue DataFrame (no external queries)."""
        logger.info("Building catalogue from SLC listings...")
        slc_df_raw = self.read_listings(slc_listings)
        if slc_df_raw.height == 0:
            logger.warning("No valid SLC entries found. The SLC part will be empty.")

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
            pl.lit([], dtype=pl.List(pl.Utf8)).alias("dataset(s) d'appartenance"),
            pl.lit(None, dtype=pl.Float32).alias("Hs WW3"),
            pl.lit(None, dtype=pl.Float32).alias("Tp WW3"),
            pl.lit(None, dtype=pl.Float32).alias("U10 ecmwf"),
            pl.lit(None, dtype=pl.Float32).alias("v10 ecmwf"),
            pl.col("start_date").alias("start date SAFE"),
            pl.lit(datetime.datetime.now()).alias("horodating"),
            pl.lit(None, dtype=pl.Utf8).alias("polygon of the acquisition from CDSE"),
            pl.lit(None, dtype=pl.Utf8).alias("S3path from CDSE"),
            pl.col("polarization").alias("polarization"),
            pl.col("mission").alias("unité"),
        ).select(list(SCHEMA.keys()))

        logger.info("Building catalogue from GRD listings...")
        grd_df_raw = self.read_listings(grd_listings)
        if grd_df_raw.height == 0:
            logger.warning("No valid GRD entries found. The GRD part will be empty.")

        grd_df = grd_df_raw.with_columns(
            pl.col("safe_name").alias("SAFE GRD"),
            pl.lit(None, dtype=pl.Utf8).alias("SAFE SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("SAFE OCN"),
            pl.lit(None, dtype=pl.Utf8).alias("presence SLC"),
            pl.lit(None, dtype=pl.Utf8).alias("presence GRD"),
            pl.lit(None, dtype=pl.Utf8).alias("presence OCN"),
            pl.lit(None, dtype=pl.Utf8).alias("presence L1B XSP A21"),
            pl.lit(None, dtype=pl.Utf8).alias("presence L1C XSP B17"),
            pl.lit([], dtype=pl.List(pl.Utf8)).alias("dataset(s) d'appartenance"),
            pl.lit(None, dtype=pl.Float32).alias("Hs WW3"),
            pl.lit(None, dtype=pl.Float32).alias("Tp WW3"),
            pl.lit(None, dtype=pl.Float32).alias("U10 ecmwf"),
            pl.lit(None, dtype=pl.Float32).alias("v10 ecmwf"),
            pl.col("start_date").alias("start date SAFE"),
            pl.lit(datetime.datetime.now()).alias("horodating"),
            pl.lit(None, dtype=pl.Utf8).alias("polygon of the acquisition from CDSE"),
            pl.lit(None, dtype=pl.Utf8).alias("S3path from CDSE"),
            pl.col("polarization").alias("polarization"),
            pl.col("mission").alias("unité"),
        ).select(list(SCHEMA.keys()))

        combined = pl.concat([slc_df, grd_df], how="vertical_relaxed").unique()
        logger.info(f"Total combined catalogue rows (before dedup): {combined.height}")
        return combined
    
    def link_slc_grd(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Link SLC and GRD products using two-step strategy:
        1. Local matching based on naming conventions and time window search
        2. CDSE fallback for orphans (using cdsodatacli)
        """
        logger.info("Linking SLC and GRD products...")
        
        # Step 1: Local matching (in-memory DataFrame operations)
        df = self._local_link_slc_grd(df)
        
        # Step 2: CDSE fallback for rows still missing links
        df = self._cdse_fallback_link(df)
        
        logger.info("SLC-GRD linking complete.")
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
        grd_rows = df.filter(pl.col("SAFE GRD").is_not_null() & pl.col("SAFE SLC").is_null())
        slc_rows = df.filter(pl.col("SAFE SLC").is_not_null() & pl.col("SAFE GRD").is_null())
        
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
                    return None
            return None
        
        # Add columns to DataFrames
        grd_rows = grd_rows.with_columns([
            pl.col("SAFE GRD").map_elements(extract_data_take_id, return_dtype=pl.Utf8).alias("data_take_id"),
            pl.col("SAFE GRD").map_elements(extract_start_time, return_dtype=pl.Datetime).alias("start_time")
        ])
        slc_rows = slc_rows.with_columns([
            pl.col("SAFE SLC").map_elements(extract_data_take_id, return_dtype=pl.Utf8).alias("data_take_id"),
            pl.col("SAFE SLC").map_elements(extract_start_time, return_dtype=pl.Datetime).alias("start_time")
        ])
        
        # Log sample data take IDs
        grd_samples = grd_rows["data_take_id"].head(3).to_list()
        slc_samples = slc_rows["data_take_id"].head(3).to_list()
        logger.info(f"GRD data_take_id samples: {grd_samples}")
        logger.info(f"SLC data_take_id samples: {slc_samples}")
        
        # Build dictionaries keyed by (mission, polarization, data_take_id) for exact matching
        slc_dict = {}  # (mission, pol, data_take_id) -> list of (slc_name, start_time)
        for row in slc_rows.to_dicts():
            mission = row.get("unité", "")
            pol = row.get("polarization", "")
            data_take_id = row.get("data_take_id", "")
            start_time = row.get("start_time")
            
            if mission and pol and data_take_id:
                key = (mission, pol, data_take_id)
                if key not in slc_dict:
                    slc_dict[key] = []
                slc_dict[key].append({
                    "safe_name": row["SAFE SLC"],
                    "start_time": start_time
                })
        
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
                logger.info(f"Local match: GRD {grd_name} -> SLC {best_match} "
                        f"(data_take_id={grd_data_take_id}, time_diff={best_time_diff:.1f}s)")
            else:
                # Check if there's any SLC with same data_take_id but time diff > 5s
                if key in slc_dict:
                    first_slc = slc_dict[key][0]["safe_name"]
                    logger.warning(f"GRD {grd_name}: No SLC within ±5s. "
                                f"Closest available SLC: {first_slc} (data_take_id={grd_data_take_id})")
        
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
        percentage = (matched_count / total_grd_needing * 100) if total_grd_needing > 0 else 0.0
        
        logger.info(f"Step 1 complete: {matched_count}/{total_grd_needing} GRD entries linked locally ({percentage:.1f}%)")
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

    def _grd_to_slc_pattern_with_offset(self, grd_name: str, offset_seconds: int) -> str:
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

    def _slc_to_grd_pattern_with_offset(self, slc_name: str, offset_seconds: int) -> str:
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
        
        logger.info(f"Found {grd_orphans.height} GRD orphans and {slc_orphans.height} SLC orphans (total {total_orphans})")
        
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
        resolved_percentage = (total_updates / total_orphans * 100) if total_orphans > 0 else 0.0
        logger.info(f"Step 2 complete: {total_updates}/{total_orphans} orphan entries resolved via CDSE ({resolved_percentage:.1f}%)")
        return df

    def _call_cdse_get_parent_slc(self, grd_name: str) -> Optional[str]:
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
            else:
                note = result.get("note", "unknown reason")
                logger.warning(f"CDSE did not find SLC for {grd_name}: {note}")
                return None
        except Exception as e:
            logger.error(f"CDSE query failed for {grd_name}: {e}")
            return None


    def _call_cdse_get_derived_grd(self, slc_name: str) -> Optional[str]:
        """
        Query CDSE to find a derived GRD for a given SLC.
        """
        try:
            from cdsodatacli.scripts.match_s1_product_types import find_product_for_safe
        except ImportError as e:
            logger.warning(f"cdsodatacli not installed: {e}. CDSE fallback disabled.")
            return None

        target_type = "GRDH"  # Most common GRD type; adjust if needed
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
        slc_listing: Union[str, Path, List],
        grd_listing: Union[str, Path, List],
    ) -> pl.DataFrame:
        """Identify SAFE not yet present in the catalogue."""
        new_raw = self.build_from_listings(slc_listing, grd_listing)
        if existing_df.height == 0:
            return new_raw

        existing_slc = set(existing_df.filter(pl.col("SAFE SLC").is_not_null())["SAFE SLC"].to_list())
        existing_grd = set(existing_df.filter(pl.col("SAFE GRD").is_not_null())["SAFE GRD"].to_list())

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

    # ---------- Placeholders for future implementation ----------
    def update_presence_columns(self, df: pl.DataFrame, force: bool = False) -> pl.DataFrame:
        return df

    def update_dataset_membership(self, df: pl.DataFrame) -> pl.DataFrame:
        return df

    def update_meteorology(self, df: pl.DataFrame, force: bool = False) -> pl.DataFrame:
        return df

    def _get_safe_centroid(self, polygon_wkt: str) -> Tuple[float, float]:
        return (0.0, 0.0)

    def _call_cdse_match(self, safe_name: str) -> List[str]:
        return []