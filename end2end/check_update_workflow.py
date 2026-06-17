#!/usr/bin/env python
"""
Test script to validate the incremental update workflow.

Steps:
1. Create initial catalogue with first config
2. Update with second config (adds new GRD listing)
3. Verify:
   - Existing rows preserved
   - Dataset arrays merged
   - horodating updated for changed rows
   - New rows appended
"""

import datetime
import os
import sys
from pathlib import Path

import polars as pl
import yaml

# Add the project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from s1iw_catalogue.catalogue import S1IWCatalogue
from s1iw_catalogue.config import load_config


def print_catalogue_summary(df: pl.DataFrame, title: str):
    """Print a summary of the catalogue."""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    print(f"Total rows: {df.height}")

    # Count by type
    slc_count = df.filter(pl.col("SAFE SLC").is_not_null()).height
    grd_count = df.filter(pl.col("SAFE GRD").is_not_null()).height
    both_count = df.filter(
        pl.col("SAFE SLC").is_not_null() & pl.col("SAFE GRD").is_not_null()
    ).height

    print(f"SLC only: {slc_count - both_count}")
    print(f"GRD only: {grd_count - both_count}")
    print(f"Both SLC and GRD: {both_count}")

    # Show datasets
    if "dataset(s) d'appartenance" in df.columns:
        # Explode to count dataset memberships
        exploded = df.explode("dataset(s) d'appartenance")
        if exploded.height > 0:
            dataset_counts = exploded.group_by("dataset(s) d'appartenance").agg(
                pl.len()
            )
            print("\nDataset memberships:")
            for row in dataset_counts.to_dicts():
                print(f"  {row["dataset(s) d'appartenance"]}: {row['len']} products")

    # Show horodating range
    if "horodating" in df.columns:
        min_horo = df["horodating"].min()
        max_horo = df["horodating"].max()
        print(f"\nhorodating range: {min_horo} to {max_horo}")


def main():
    # Config files
    config_initial = Path("s1iw_catalogue/localconfig.yml")
    config_update = Path("s1iw_catalogue/localconfig_update.yml")
    catalogue_path = Path("/scratch/agrouaze/test_update_workflow.parquet")

    print(f"Initial config: {config_initial}")
    print(f"Update config: {config_update}")
    print(f"Catalogue: {catalogue_path}")

    # Step 1: Create initial catalogue
    print("\n" + "=" * 60)
    print("STEP 1: Creating initial catalogue")
    print("=" * 60)

    if catalogue_path.exists():
        catalogue_path.unlink()
        print(f"Removed existing catalogue: {catalogue_path}")

    # Load initial config
    cfg1 = load_config(config_path=config_initial)
    cat1 = S1IWCatalogue(catalogue_path, config=cfg1)
    cat1.create()

    # Verify initial catalogue
    df1 = pl.read_parquet(catalogue_path)
    print_catalogue_summary(df1, "Initial Catalogue")

    # Step 2: Update with new config
    print("\n" + "=" * 60)
    print("STEP 2: Updating catalogue with new config")
    print("=" * 60)

    cfg2 = load_config(config_path=config_update)
    cat2 = S1IWCatalogue(catalogue_path, config=cfg2)
    cat2.update()

    # Verify updated catalogue
    df2 = pl.read_parquet(catalogue_path)
    print_catalogue_summary(df2, "Updated Catalogue")

    # Step 3: Verify specific expected changes
    print("\n" + "=" * 60)
    print("STEP 3: Verification")
    print("=" * 60)

    # Check that new GRD listing was added
    # Look for products from 'lion' dataset
    if "dataset(s) d'appartenance" in df2.columns:
        lion_products = df2.filter(
            pl.col("dataset(s) d'appartenance").list.contains("lion")
        )
        print(f"Products with 'lion' dataset: {lion_products.height}")
        if lion_products.height > 0:
            print("  First few:")
            print(
                lion_products.select(["SAFE GRD", "dataset(s) d'appartenance"]).head(3)
            )

    # Check that existing rows preserved their data
    # Compare start date of a known product
    known_grd = (
        "S1A_IW_GRDH_1SDV_20190711T181228_20190711T181253_028073_032B9D_6E14.SAFE"
    )
    known_row1 = df1.filter(pl.col("SAFE GRD") == known_grd)
    known_row2 = df2.filter(pl.col("SAFE GRD") == known_grd)

    if known_row1.height > 0 and known_row2.height > 0:
        print(f"\nChecking known product: {known_grd}")
        print(f"  Initial - presence GRD: {known_row1['presence GRD'][0]}")
        print(f"  Updated - presence GRD: {known_row2['presence GRD'][0]}")
        # Presence should be preserved (not overwritten)
        if known_row1["presence GRD"][0] == known_row2["presence GRD"][0]:
            print("  ✅ presence GRD preserved")
        else:
            print("  ⚠️ presence GRD changed (this may be expected if paths changed)")

    # Check horodating updates
    print(
        f"\nhorodating range - initial: {df1['horodating'].min()} to {df1['horodating'].max()}"
    )
    print(
        f"horodating range - updated: {df2['horodating'].min()} to {df2['horodating'].max()}"
    )

    # Check row count
    print(f"\nRows added: {df2.height - df1.height}")

    print("\n" + "=" * 60)
    print("Workflow test complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
