#!/usr/bin/env python3
"""
end2end/create_dummy_catalogue_with_ww3.py

Creates a dummy catalogue with fake SAR polygons in the Iroise Sea,
extracts WW3 values for each polygon, and plots the results on a map.
"""

from typing import Any, Dict, List, Optional, Tuple

import argparse
import logging
import os
import sys
import warnings
from datetime import datetime, timedelta

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from cartopy.mpl.gridliner import LATITUDE_FORMATTER, LONGITUDE_FORMATTER
from shapely import wkt
from shapely.geometry import box

warnings.filterwarnings("ignore")

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from s1iw_catalogue.ww3_extractor import add_ww3_to_catalogue

# Set up logger
logger = logging.getLogger(__name__)


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Set up logging with the specified level."""
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


def create_dummy_catalogue(
    lon_min: float = -6.0,
    lon_max: float = -3.0,
    lat_min: float = 47.0,
    lat_max: float = 49.0,
    step_deg: float = 0.45,
    polygon_size_deg: float = 0.18,
    date_start: str = "2023-01-15 12:00:00",
    n_products_per_location: int = 1,
) -> pd.DataFrame:
    """
    Create a dummy catalogue with fake SAR polygons in the Iroise Sea.

    Args:
        lon_min, lon_max, lat_min, lat_max: Bounding box for the grid
        step_deg: Spacing between grid points in degrees (~50km)
        polygon_size_deg: Size of each polygon in degrees (~20km)
        date_start: Start date for the products
        n_products_per_location: Number of products per location

    Returns:
        DataFrame with dummy catalogue
    """
    logger.info("=" * 60)
    logger.info("📍 Creating dummy catalogue for Iroise Sea")
    logger.info(
        "   Grid: lon [%.2f, %.2f], lat [%.2f, %.2f]",
        lon_min,
        lon_max,
        lat_min,
        lat_max,
    )
    logger.info("   Step: %.3f° (~%.1fkm)", step_deg, step_deg * 111)
    logger.info(
        "   Polygon size: %.3f° (~%.1fkm)",
        polygon_size_deg,
        polygon_size_deg * 111,
    )
    logger.info("=" * 60)

    # Create grid points
    lons = np.arange(lon_min, lon_max + step_deg, step_deg)
    lats = np.arange(lat_min, lat_max + step_deg, step_deg)

    products = []
    product_id = 0

    start_date = pd.to_datetime(date_start)

    for lon in lons:
        for lat in lats:
            # Create a square polygon around the point
            half_size = polygon_size_deg / 2
            polygon = box(
                lon - half_size, lat - half_size, lon + half_size, lat + half_size
            )

            for k in range(n_products_per_location):
                # Create different times for each product at the same location
                product_time = start_date + timedelta(hours=k * 3)

                product = {
                    "SAFE SLC": f"DUMMY_SLC_{product_id:06d}",
                    "SAFE GRD": f"DUMMY_GRD_{product_id:06d}",
                    "SAFE OCN": f"DUMMY_OCN_{product_id:06d}",
                    "presence SLC": 1,
                    "presence GRD": 1,
                    "presence OCN": 1,
                    "presence L1B XSP A21": 0,
                    "presence L1C XSP B17": 0,
                    "dataset(s) d'appartenance": ["dummy"],
                    "dataset_category": "dummy",
                    "Hs WW3": np.nan,
                    "Tp WW3": np.nan,
                    "U10 ecmwf": np.nan,
                    "V10 ecmwf": np.nan,
                    "start date SAFE": product_time,
                    "horodating": datetime.now(),
                    "polygon SLC": polygon.wkt,
                    "polygon GRD": polygon.wkt,
                    "S3path SLC": f"/dummy/path/SLC_{product_id:06d}",
                    "S3path GRD": f"/dummy/path/GRD_{product_id:06d}",
                    "polarization": "VV",
                    "unité": "S1A",
                    "presence L1B XSP A23": 0,
                    "presence L1C XSP B21": 0,
                    "presence L2 WAV E11": 0,
                    "presence L2 WAV E13": 0,
                }
                products.append(product)
                product_id += 1

    df = pd.DataFrame(products)

    # Add geometry column as shapely objects for convenience
    df["geometry"] = df["polygon SLC"].apply(wkt.loads)

    logger.info("✅ Created %d dummy products", len(df))
    logger.info(
        "   Grid: %d x %d = %d locations", len(lons), len(lats), len(lons) * len(lats)
    )
    logger.info(
        "   Time range: %s to %s",
        df["start date SAFE"].min(),
        df["start date SAFE"].max(),
    )

    return df


def extract_ww3_for_catalogue(
    catalogue_df: pd.DataFrame,
    config_path: str | None = None,
    n_jobs: int = 4,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Extract WW3 values for all products in the catalogue.
    """
    logger.info("\n" + "=" * 60)
    logger.info("🌊 Extracting WW3 values from dummy catalogue")
    logger.info("=" * 60)

    # Convert to GeoDataFrame if needed
    if "geometry" not in catalogue_df.columns:
        catalogue_df["geometry"] = catalogue_df["polygon SLC"].apply(wkt.loads)

    # Extract WW3 data
    result_df = add_ww3_to_catalogue(
        catalogue_df, config_path=config_path, n_jobs=n_jobs, verbose=verbose
    )

    # Count successful extractions
    valid_hs = result_df["Hs WW3"].notna().sum()
    valid_tp = result_df["Tp WW3"].notna().sum()
    total = len(result_df)

    logger.info("✅ WW3 extraction complete:")
    logger.info("   Hs WW3: %d/%d valid", valid_hs, total)
    logger.info("   Tp WW3: %d/%d valid", valid_tp, total)

    return result_df


def _get_plot_data(
    catalogue_df: pd.DataFrame, var_name: str
) -> tuple[np.ndarray, np.ndarray]:
    """
    Extract centroids and values for plotting.

    Returns:
        Tuple of (centroids_array, values_array)
    """
    centroids = []
    values = []
    valid_products = catalogue_df[catalogue_df[var_name].notna()]

    for _, row in valid_products.iterrows():
        try:
            polygon = wkt.loads(row["polygon SLC"])
            centroid = polygon.centroid
            centroids.append((centroid.x, centroid.y))
            values.append(row[var_name])
        except Exception as e:
            logger.debug("Error processing product: %s", e)

    return np.array(centroids), np.array(values)


def _add_map_features(ax, draw_labels: bool = True) -> None:
    """Add standard map features to a Cartopy axis."""
    ax.add_feature(cfeature.LAND, facecolor="lightgray", edgecolor="black", alpha=0.7)
    ax.add_feature(cfeature.OCEAN, facecolor="lightblue", alpha=0.3)
    ax.add_feature(cfeature.COASTLINE, linewidth=0.8)
    ax.add_feature(cfeature.BORDERS, linewidth=0.5, linestyle=":")
    ax.add_feature(cfeature.LAKES, facecolor="lightblue", alpha=0.5)
    ax.add_feature(cfeature.RIVERS, linewidth=0.5)

    if draw_labels:
        gl = ax.gridlines(
            draw_labels=True, linewidth=0.5, color="gray", alpha=0.5, linestyle="--"
        )
        gl.top_labels = False
        gl.right_labels = False
        gl.xformatter = LONGITUDE_FORMATTER
        gl.yformatter = LATITUDE_FORMATTER


def _create_scatter_plot(
    ax,
    centroids: np.ndarray,
    values: np.ndarray,
    vmin: float,
    vmax: float,
    cmap: str,
) -> Any:
    """Create a scatter plot on a Cartopy axis."""
    return ax.scatter(
        centroids[:, 0],
        centroids[:, 1],
        c=values,
        s=80,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        transform=ccrs.PlateCarree(),
        edgecolor="black",
        linewidth=0.5,
        alpha=0.85,
        zorder=10,
    )


def plot_ww3_map(
    catalogue_df: pd.DataFrame,
    output_dir: str,
    var_name: str = "Hs WW3",
    title: str | None = None,
    vmin: float | None = None,
    vmax: float | None = None,
    cmap: str = "viridis",
    log_level: str = "INFO",
) -> None:
    """
    Plot WW3 variables on a map using Cartopy.
    """
    _ = setup_logging(log_level)  # Reuse existing logger

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Get plot data
    centroids, values = _get_plot_data(catalogue_df, var_name)

    if len(centroids) == 0:
        logger.error("No valid data to plot for %s", var_name)
        return

    # Set colorbar limits if not provided
    if vmin is None:
        vmin = values.min() * 0.9 if len(values) > 0 else 0
    if vmax is None:
        vmax = values.max() * 1.1 if len(values) > 0 else 10

    logger.info(
        "📊 Plotting %s: %d points, range [%.2f, %.2f]",
        var_name,
        len(values),
        vmin,
        vmax,
    )

    # Create figure with Cartopy projection
    fig, ax = plt.subplots(
        figsize=(12, 10), subplot_kw={"projection": ccrs.PlateCarree()}
    )

    # Set map extent
    lon_min, lon_max = centroids[:, 0].min() - 0.5, centroids[:, 0].max() + 0.5
    lat_min, lat_max = centroids[:, 1].min() - 0.5, centroids[:, 1].max() + 0.5
    ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())

    # Add map features
    _add_map_features(ax)

    # Create scatter plot
    scatter = _create_scatter_plot(ax, centroids, values, vmin, vmax, cmap)

    # Add colorbar
    cbar = fig.colorbar(scatter, ax=ax, orientation="vertical", pad=0.05)

    # Set colorbar label
    cbar_label = {
        "Hs WW3": "Significant Wave Height (m)",
        "Tp WW3": "Peak Period (s)",
    }.get(var_name, var_name)
    cbar.set_label(cbar_label, fontsize=12)

    # Set title
    if title is None:
        title = f"{var_name} - Iroise Sea"
    ax.set_title(title, fontsize=14, pad=20)

    # Add timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ax.text(
        0.02,
        0.02,
        f"Generated: {timestamp}",
        transform=ax.transAxes,
        fontsize=8,
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.8},
    )

    # Save figure
    output_file = os.path.join(output_dir, f"{var_name.replace(' ', '_')}_map.png")
    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches="tight")
    plt.close()

    logger.info("✅ Saved plot to: %s", output_file)

    # Also create a combined plot with both variables
    plot_combined_map(catalogue_df, output_dir, log_level=log_level)


def plot_combined_map(
    catalogue_df: pd.DataFrame,
    output_dir: str,
    log_level: str = "INFO",
) -> None:
    """
    Create a combined plot with both Hs and Tp side by side.
    """
    _ = setup_logging(log_level)  # Reuse existing logger

    os.makedirs(output_dir, exist_ok=True)

    # Get data for both variables
    centroids_hs, values_hs = _get_plot_data(catalogue_df, "Hs WW3")
    centroids_tp, values_tp = _get_plot_data(catalogue_df, "Tp WW3")

    if len(centroids_hs) == 0 or len(centroids_tp) == 0:
        logger.error("No valid data for combined plot")
        return

    # Set extents
    all_centroids = np.vstack([centroids_hs, centroids_tp])
    lon_min, lon_max = all_centroids[:, 0].min() - 0.5, all_centroids[:, 0].max() + 0.5
    lat_min, lat_max = all_centroids[:, 1].min() - 0.5, all_centroids[:, 1].max() + 0.5

    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(16, 8), subplot_kw={"projection": ccrs.PlateCarree()}
    )

    # Plot configurations
    plot_configs = [
        (ax1, "Hs WW3", centroids_hs, values_hs, "viridis"),
        (ax2, "Tp WW3", centroids_tp, values_tp, "plasma"),
    ]

    for ax, var_name, centroids, values, cmap in plot_configs:
        ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())

        # Add map features
        _add_map_features(ax)

        # Calculate color limits
        vmin = values.min() * 0.9
        vmax = values.max() * 1.1

        # Scatter plot
        scatter = _create_scatter_plot(ax, centroids, values, vmin, vmax, cmap)

        # Colorbar
        cbar = fig.colorbar(scatter, ax=ax, orientation="vertical", pad=0.05)
        if var_name == "Hs WW3":
            cbar.set_label("Significant Wave Height (m)", fontsize=10)
        else:
            cbar.set_label("Peak Period (s)", fontsize=10)

        # Title
        ax.set_title(var_name, fontsize=12)

    # Overall title
    fig.suptitle("WW3 Variables - Iroise Sea", fontsize=14)

    # Save figure
    output_file = os.path.join(output_dir, "WW3_combined_map.png")
    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches="tight")
    plt.close()

    logger.info("✅ Saved combined plot to: %s", output_file)


def _parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Create dummy catalogue and extract WW3 values",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create catalogue and extract WW3 (default)
  python create_dummy_catalogue_with_ww3.py --output_png_dir ./ww3_maps

  # Custom grid and log level
  python create_dummy_catalogue_with_ww3.py --output_png_dir ./ww3_maps \\
      --step_deg 0.5 --log_level DEBUG

  # Save catalogue to file
  python create_dummy_catalogue_with_ww3.py --output_png_dir ./ww3_maps \\
      --output_catalogue ./dummy_catalogue.parquet
        """,
    )

    parser.add_argument(
        "--output_png_dir", required=True, help="Output directory for PNG maps"
    )
    parser.add_argument(
        "--output_catalogue", help="Output path for the dummy catalogue (.parquet)"
    )
    parser.add_argument(
        "--config_path",
        default="s1iw_catalogue/localconfig_second_real.yml",
        help="Path to config file (default: s1iw_catalogue/localconfig_second_real.yml)",
    )
    parser.add_argument(
        "--step_deg",
        type=float,
        default=0.45,
        help="Grid spacing in degrees (~50km default)",
    )
    parser.add_argument(
        "--polygon_size_deg",
        type=float,
        default=0.18,
        help="Polygon size in degrees (~20km default)",
    )
    parser.add_argument(
        "--date_start",
        default="2023-01-15 12:00:00",
        help="Start date for products (format: YYYY-MM-DD HH:MM:SS)",
    )
    parser.add_argument(
        "--n_products_per_location",
        type=int,
        default=1,
        help="Number of products per grid location (for time variation)",
    )
    parser.add_argument(
        "--n_jobs",
        type=int,
        default=4,
        help="Number of parallel jobs for WW3 extraction (default: 4)",
    )
    parser.add_argument(
        "--log_level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--skip_extraction",
        action="store_true",
        help="Skip WW3 extraction (only create catalogue and plot)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force WW3 extraction even if columns exist",
    )
    parser.add_argument(
        "--lon_min", type=float, default=-6.0, help="Minimum longitude (default: -6.0)"
    )
    parser.add_argument(
        "--lon_max", type=float, default=-3.0, help="Maximum longitude (default: -3.0)"
    )
    parser.add_argument(
        "--lat_min", type=float, default=47.0, help="Minimum latitude (default: 47.0)"
    )
    parser.add_argument(
        "--lat_max", type=float, default=49.0, help="Maximum latitude (default: 49.0)"
    )

    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    args = _parse_arguments()

    # Setup logging
    logger = setup_logging(args.log_level)

    logger.info("=" * 60)
    logger.info("🚀 Starting dummy catalogue creation with WW3 extraction")
    logger.info("=" * 60)

    # Step 1: Create dummy catalogue
    catalogue_df = create_dummy_catalogue(
        lon_min=args.lon_min,
        lon_max=args.lon_max,
        lat_min=args.lat_min,
        lat_max=args.lat_max,
        step_deg=args.step_deg,
        polygon_size_deg=args.polygon_size_deg,
        date_start=args.date_start,
        n_products_per_location=args.n_products_per_location,
    )

    # Step 2: Extract WW3 values (unless skipped)
    if not args.skip_extraction:
        catalogue_df = extract_ww3_for_catalogue(
            catalogue_df,
            config_path=args.config_path,
            n_jobs=args.n_jobs,
            verbose=True,
        )

    # Step 3: Save catalogue if requested
    if args.output_catalogue:
        catalogue_df.to_parquet(args.output_catalogue)
        logger.info("✅ Saved catalogue to: %s", args.output_catalogue)

    # Step 4: Create maps
    logger.info("\n" + "=" * 60)
    logger.info("🗺️ Creating maps...")
    logger.info("=" * 60)

    # Plot Hs WW3
    plot_ww3_map(
        catalogue_df,
        args.output_png_dir,
        var_name="Hs WW3",
        title=f"Hs WW3 - Iroise Sea ({args.date_start[:10]})",
        cmap="viridis",
        log_level=args.log_level,
    )

    # Plot Tp WW3
    plot_ww3_map(
        catalogue_df,
        args.output_png_dir,
        var_name="Tp WW3",
        title=f"Tp WW3 - Iroise Sea ({args.date_start[:10]})",
        cmap="plasma",
        log_level=args.log_level,
    )

    # Combined plot
    plot_combined_map(catalogue_df, args.output_png_dir, log_level=args.log_level)

    logger.info("\n" + "=" * 60)
    logger.info("✅ All done!")
    logger.info("📁 Maps saved to: %s", args.output_png_dir)
    if args.output_catalogue:
        logger.info("📁 Catalogue saved to: %s", args.output_catalogue)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
