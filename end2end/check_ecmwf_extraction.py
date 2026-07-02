"""End-to-end test script for ECMWF wind data extraction."""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from s1iw_catalogue.config import load_config
from s1iw_catalogue.schema import ECMWF_COLUMNS
from s1iw_catalogue.updater import CatalogueUpdater


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """
    Configure basic logging for the script.

    Args:
        log_level: String representation of the log level (e.g., 'INFO', 'DEBUG')

    Returns:
        Configured logger instance
    """
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    level = level_map.get(log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


def example_usage(
    config_path: str,
    input_path_catalogue: str,
    output_path_catalogue: str,
    log_level: str = "INFO",
    n_jobs: int = 8,
    force: bool = False,
) -> pd.DataFrame | None:
    """
    Test ECMWF extraction on a catalogue.

    Args:
        config_path: Path to the YAML configuration file
        input_path_catalogue: Path to the input catalogue (.parquet or .pkl)
        output_path_catalogue: Path where the output will be saved
        log_level: Logging verbosity
        n_jobs: Number of parallel workers for extraction
        force: If True, overwrites existing ECMWF values

    Returns:
        Updated catalogue DataFrame, or None if it fails
    """
    logger = setup_logging(log_level)

    logger.info("=" * 60)
    logger.info("🚀 Starting ECMWF extraction test (FAST mode)")
    logger.info(f"   Log level: {log_level}")
    logger.info(f"   Jobs: {n_jobs}")
    logger.info(f"   Force update: {force}")
    logger.info("=" * 60)

    # Load catalogue
    logger.info(f"📂 Loading catalogue from: {input_path_catalogue}")
    if input_path_catalogue.endswith(".parquet"):
        catalogue = pd.read_parquet(input_path_catalogue)
    elif input_path_catalogue.endswith(".pkl"):
        catalogue = pd.read_pickle(input_path_catalogue)
    else:
        raise ValueError(f"Unsupported file format: {input_path_catalogue}")

    logger.info(f"📊 Loaded catalogue with {len(catalogue)} products")
    logger.debug(f"   Columns: {catalogue.columns.tolist()}")

    # Check required columns
    if "start date SAFE" not in catalogue.columns:
        logger.error("❌ Missing 'start date SAFE' column")
        logger.info(f"   Available columns: {catalogue.columns.tolist()}")
        return None

    geom_cols = ["geometry", "polygon SLC", "polygon GRD", "polygon"]
    found_geom = [col for col in geom_cols if col in catalogue.columns]
    if not found_geom:
        logger.error("❌ No geometry column found")
        logger.info(f"   Available columns: {catalogue.columns.tolist()}")
        return None
    logger.info(f"   Using geometry column: {found_geom[0]}")

    # Initialize updater
    logger.info("🔧 Initializing CatalogueUpdater...")
    updater = CatalogueUpdater(config_path=config_path)

    # Add ECMWF data
    logger.info("\n🌬️ Adding ECMWF data (FAST mode - nearest grid point)...")

    catalogue_with_ecmwf = updater.update_with_ecmwf(
        catalogue,
        n_jobs=n_jobs,
        force_update=force,
        verbose=True,
    )

    # Check results
    logger.info("\n📊 Results summary:")
    for col in ECMWF_COLUMNS:
        if col in catalogue_with_ecmwf.columns:
            null_count = catalogue_with_ecmwf[col].isna().sum()
            valid_count = len(catalogue_with_ecmwf) - null_count
            logger.info(f"   {col}: {valid_count}/{len(catalogue_with_ecmwf)} values")
        else:
            logger.warning(f"   {col}: MISSING")

    # Show sample
    if "U10 ecmwf" in catalogue_with_ecmwf.columns:
        sample = catalogue_with_ecmwf[["U10 ecmwf", "V10 ecmwf"]].head()
        logger.info("\n📋 Sample of extracted values:")
        logger.info(f"\n{sample.to_string()}")

    logger.info("=" * 60)
    logger.info("✅ ECMWF extraction test completed")
    logger.info("=" * 60)

    return catalogue_with_ecmwf


def main() -> None:
    """Parse arguments and run the ECMWF extraction test."""
    parser = argparse.ArgumentParser(
        description="Test ECMWF wind extraction (FAST mode)"
    )

    parser.add_argument(
        "--input_path_catalogue",
        required=True,
        help="Path to input catalogue file (.parquet or .pkl)",
    )
    parser.add_argument(
        "--output_path_catalogue",
        required=True,
        help="Path to output catalogue file (.parquet)",
    )
    parser.add_argument(
        "--config_path",
        default="s1iw_catalogue/localconfig_second_real.yml",
        help="Path to config file",
    )
    parser.add_argument(
        "--log_level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--n_jobs",
        type=int,
        default=8,
        help="Number of parallel jobs (default: 8)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force recalculation even if ECMWF columns already exist",
    )

    args = parser.parse_args()

    result = example_usage(
        config_path=args.config_path,
        input_path_catalogue=args.input_path_catalogue,
        output_path_catalogue=args.output_path_catalogue,
        log_level=args.log_level,
        n_jobs=args.n_jobs,
        force=args.force,
    )

    if result is not None:
        result.to_parquet(args.output_path_catalogue)
        print(f"\n✅ Saved to: {args.output_path_catalogue}")
    else:
        print("\n❌ Failed to process catalogue")
        sys.exit(1)


if __name__ == "__main__":
    main()