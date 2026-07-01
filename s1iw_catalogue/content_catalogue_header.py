#!/usr/bin/env python
"""Quick script to display the header (first rows) of a catalogue Parquet file."""

import argparse
import sys
from pathlib import Path

import polars as pl


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Display the first rows of a Sentinel-1 IW catalogue Parquet file."
    )
    parser.add_argument(
        "--path-catalogue",
        required=True,
        type=Path,
        help="Path to the catalogue .parquet file.",
    )
    parser.add_argument(
        "--nrows",
        type=int,
        default=10,
        help="Number of rows to display (default: 10).",
    )
    parser.add_argument(
        "--columns",
        type=str,
        nargs="+",
        help="Columns to show (default: key columns).",
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Show all columns (by default only key columns are shown).",
    )
    parser.add_argument(
        "--format",
        choices=["table", "glimpse"],
        default="table",
        help="Output format: 'table' (default) or 'glimpse' (compact row-wise view).",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show summary statistics instead of rows.",
    )
    parser.add_argument(
        "--cell-width",
        type=int,
        default=100,
        help="Maximum characters per cell (default: 100).",
    )
    args = parser.parse_args()
    pl.Config.set_fmt_str_lengths(args.cell_width)
    if not args.path_catalogue.exists():
        print(f"Error: Catalogue file not found: {args.path_catalogue}")
        sys.exit(1)

    # Read the catalogue with Polars
    df = pl.read_parquet(args.path_catalogue)

    if args.summary:
        print("Catalogue summary:")
        print(f"  Shape: {df.shape}")
        print("  Column types:")
        for col in df.columns:
            print(f"    {col}: {df[col].dtype}")
        print(f"  Missing values per column:")
        for col in df.columns:
            nulls = df[col].null_count()
            print(f"    {col}: {nulls} ({nulls/df.height*100:.1f}%)")
        return

    # Select columns
    if not args.columns and not args.show_all:
        # Default key columns: SAFE SLC, SAFE GRD, start date, horodating, polarization, unit
        default_cols = [
            "SAFE SLC",
            "SAFE GRD",
            "start date SAFE",
            "horodating",
            "polarization",
            "unit",
        ]
        cols_to_show = [c for c in default_cols if c in df.columns]
    elif args.columns:
        missing = [c for c in args.columns if c not in df.columns]
        if missing:
            print(f"Warning: columns {missing} not found in catalogue.")
        cols_to_show = [c for c in args.columns if c in df.columns]
    else:
        cols_to_show = df.columns

    df_subset = df.select(cols_to_show).head(args.nrows)

    # Configure Polars display to avoid wrapping
    pl.Config.set_tbl_width_chars(200)
    pl.Config.set_tbl_cols(200)  # Not a real config, but we can set

    if args.format == "glimpse":
        # Glimpse shows each row with column-value pairs, good for wide data
        df_subset.glimpse()
    else:
        print(df_subset)


if __name__ == "__main__":
    main()
