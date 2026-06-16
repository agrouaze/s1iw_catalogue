"""Incremental update logic for the catalogue."""

import datetime
import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple, Union

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