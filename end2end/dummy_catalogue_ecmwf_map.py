#!/usr/bin/env python3
"""
End-to-end test creating a dummy catalogue with fake SAR polygons,
extracting ECMWF 10m wind values, and plotting the results on a map.
"""

import argparse
import logging
import os
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from cartopy import crs as ccrs
from cartopy import feature as cfeature
from cartopy.mpl.gridliner import LATITUDE_FORMATTER, LONGITUDE_FORMATTER
from shapely import wkt
from shapely.geometry import box

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from s1iw_catalogue.ecmwf_extractor import add_ecmwf_to_catalogue
from s1iw_catalogue.schema import ECMWF_COLUMNS

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """
    Set up logging with the specified level.

    Args:
        log_level: String representation of the log level

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
        lon_min: Minimum longitude
        lon_max: Maximum longitude
        lat_min: Minimum latitude
        lat_max: Maximum latitude
        step_deg: Spacing between grid points in degrees
        polygon_size_deg: Size of each polygon in degrees
        date_start: Start date for the products
        n_products_per_location: Number of products per location

    Returns:
        DataFrame with dummy catalogue
    """
    logger.info("=" * 60)
    logger.info("📍 Creating dummy catalogue for Iroise Sea")
    logger.info(
        f"   Grid: lon [{lon_min:.2f}, {lon_max:.2f}], lat [{lat_min:.2f}, {lat_max:.2f}]"
    )
    logger.info(f"   Step: {step_deg:.3f}° (~{step_deg * 111:.1f}km)")
    logger.info(
        f"   Polygon size: {polygon_size_deg:.3f}° (~{polygon_size_deg * 111:.1f}km)"
    )
    logger.info("=" * 60)

    lons = np.arange(lon_min, lon_max + step_deg, step_deg)
    lats = np.arange(lat_min, lat_max + step_deg, step_deg)

    products = []
    product_id = 0
    start_date = pd.to_datetime(date_start)

    for lon in lons:
        for lat in lats:
            half_size = polygon_size_deg / 2
            polygon = box(
                lon - half_size, lat - half_size, lon + half_size, lat + half_size
            )

            for k in range(n_products_per_location):
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
                }
                products.append(product)
                product_id += 1

    df = pd.DataFrame(products)
    df["geometry"] = df["polygon SLC"].apply(wkt.loads)

    logger.info(f"✅ Created {len(df)} dummy products")
    logger.info(
        f"   Grid: {len(lons)} x {len(lats)} = {len(lons) * len(lats)} locations"
    )
    logger.info(
        f"   Time range: {df['start date SAFE'].min()} to {df['start date SAFE'].max()}"
    )

    return df


def extract_ecmwf_for_catalogue(
    catalogue_df: pd.DataFrame,
    config_path: str | None = None,
    n_jobs: int = 4,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Extract ECMWF 10m wind values for all products in the catalogue.

    Args:
        catalogue_df: Input catalogue DataFrame
        config_path: Path to YAML configuration
        n_jobs: Number of parallel workers
        verbose: Enable logging

    Returns:
        DataFrame with ECMWF columns populated
    """
    logger.info("\n" + "=" * 60)
    logger.info("🌬️ Extracting ECMWF values from dummy catalogue")
    logger.info("=" * 60)

    if "geometry" not in catalogue_df.columns:
        catalogue_df["geometry"] = catalogue_df["polygon SLC"].apply(wkt.loads)

    result_df = add_ecmwf_to_catalogue(
        catalogue_df, config_path=config_path, n_jobs=n_jobs, verbose=verbose
    )

    valid_u = result_df["U10 ecmwf"].notna().sum()
    valid_v = result_df["V10 ecmwf"].notna().sum()
    total = len(result_df)

    logger.info("✅ ECMWF extraction complete:")
    logger.info(f"   U10 ecmwf: {valid_u}/{total} valid")
    logger.info(f"   V10 ecmwf: {valid_v}/{total} valid")

    return result_df


def plot_ecmwf_map(
    catalogue_df: pd.DataFrame,
    output_dir: str,
    var_name: str = "U10 ecmwf",
    title: str | None = None,
    vmin: float | None = None,
    vmax: float | None = None,
    cmap: str = "RdBu_r",
    log_level: str = "INFO",
) -> None:
    """
    Plot an ECMWF variable on a map using Cartopy.

    Args:
        catalogue_df: DataFrame with ECMWF values and polygons
        output_dir: Output directory for PNG files
        var_name: Variable to plot
        title: Custom title for the plot
        vmin: Colorbar minimum limit
        vmax: Colorbar maximum limit
        cmap: Colormap name
        log_level: Logging level
    """
    _ = setup_logging(log_level)
    os.makedirs(output_dir, exist_ok=True)

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
            logger.debug(f"Error processing product: {e}")

    if not centroids:
        logger.error(f"No valid data to plot for {var_name}")
        return

    centroids = np.array(centroids)
    values = np.array(values)

    if vmin is None:
        vmin = values.min() * 1.1 if values.min() < 0 else values.min() * 0.9
    if vmax is None:
        vmax = values.max() * 1.1 if values.max() > 0 else values.max() * 0.9

    logger.info(
        f"📊 Plotting {var_name}: {len(values)} points, range [{vmin:.2f}, {vmax:.2f}]"
    )

    fig, ax = plt.subplots(
        figsize=(12, 10), subplot_kw={"projection": ccrs.PlateCarree()}
    )

    lon_min, lon_max = centroids[:, 0].min() - 0.5, centroids[:, 0].max() + 0.5
    lat_min, lat_max = centroids[:, 1].min() - 0.5, centroids[:, 1].max() + 0.5
    ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())

    ax.add_feature(cfeature.LAND, facecolor="lightgray", edgecolor="black", alpha=0.7)
    ax.add_feature(cfeature.OCEAN, facecolor="lightblue", alpha=0.3)
    ax.add_feature(cfeature.COASTLINE, linewidth=0.8)
    ax.add_feature(cfeature.BORDERS, linewidth=0.5, linestyle=":")

    gl = ax.gridlines(
        draw_labels=True, linewidth=0.5, color="gray", alpha=0.5, linestyle="--"
    )
    gl.top_labels = False
    gl.right_labels = False
    gl.xformatter = LONGITUDE_FORMATTER
    gl.yformatter = LATITUDE_FORMATTER

    scatter = ax.scatter(
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

    cbar = fig.colorbar(scatter, ax=ax, orientation="vertical", pad=0.05)
    cbar_label = (
        "10m U-component (m/s)" if "U10" in var_name else "10m V-component (m/s)"
    )
    cbar.set_label(cbar_label, fontsize=12)

    ax.set_title(title if title else f"{var_name} - Iroise Sea", fontsize=14, pad=20)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ax.text(
        0.02,
        0.02,
        f"Generated: {timestamp}",
        transform=ax.transAxes,
        fontsize=8,
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
    )

    output_file = os.path.join(output_dir, f"{var_name.replace(' ', '_')}_map.png")
    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info(f"✅ Saved plot to: {output_file}")


def plot_combined_map(
    catalogue_df: pd.DataFrame,
    output_dir: str,
    log_level: str = "INFO",
) -> None:
    """
    Create a combined plot showing Wind Speed magnitude derived from U10 and V10.

    Args:
        catalogue_df: DataFrame with U10 and V10 values
        output_dir: Output directory for the PNG file
        log_level: Logging level
    """
    _ = setup_logging(log_level)
    os.makedirs(output_dir, exist_ok=True)

    centroids = []
    speeds = []
    valid_products = catalogue_df[
        catalogue_df["U10 ecmwf"].notna() & catalogue_df["V10 ecmwf"].notna()
    ]

    for _, row in valid_products.iterrows():
        try:
            polygon = wkt.loads(row["polygon SLC"])
            centroid = polygon.centroid
            centroids.append((centroid.x, centroid.y))
            # Calculate wind speed magnitude
            u = row["U10 ecmwf"]
            v = row["V10 ecmwf"]
            speeds.append(np.sqrt(u**2 + v**2))
        except Exception:
            pass

    if not centroids:
        logger.error("No valid data for combined wind speed plot")
        return

    centroids = np.array(centroids)
    speeds = np.array(speeds)

    fig, ax = plt.subplots(
        figsize=(12, 10), subplot_kw={"projection": ccrs.PlateCarree()}
    )

    lon_min, lon_max = centroids[:, 0].min() - 0.5, centroids[:, 0].max() + 0.5
    lat_min, lat_max = centroids[:, 1].min() - 0.5, centroids[:, 1].max() + 0.5
    ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())

    ax.add_feature(cfeature.LAND, facecolor="lightgray", edgecolor="black", alpha=0.7)
    ax.add_feature(cfeature.OCEAN, facecolor="lightblue", alpha=0.3)
    ax.add_feature(cfeature.COASTLINE, linewidth=0.8)

    gl = ax.gridlines(
        draw_labels=True, linewidth=0.5, color="gray", alpha=0.5, linestyle="--"
    )
    gl.top_labels = False
    gl.right_labels = False
    gl.xformatter = LONGITUDE_FORMATTER
    gl.yformatter = LATITUDE_FORMATTER

    scatter = ax.scatter(
        centroids[:, 0],
        centroids[:, 1],
        c=speeds,
        s=80,
        cmap="YlOrRd",
        vmin=0,
        vmax=speeds.max() * 1.1,
        transform=ccrs.PlateCarree(),
        edgecolor="black",
        linewidth=0.5,
        alpha=0.85,
        zorder=10,
    )

    cbar = fig.colorbar(scatter, ax=ax, orientation="vertical", pad=0.05)
    cbar.set_label("10m Wind Speed (m/s)", fontsize=12)
    ax.set_title("ECMWF 10m Wind Speed - Iroise Sea", fontsize=14, pad=20)

    output_file = os.path.join(output_dir, "ECMWF_Wind_Speed_map.png")
    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info(f"✅ Saved combined wind speed plot to: {output_file}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create dummy catalogue and extract ECMWF values"
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
        help="Path to config file",
    )
    parser.add_argument(
        "--step_deg", type=float, default=0.45, help="Grid spacing in degrees"
    )
    parser.add_argument(
        "--date_start", default="2023-01-15 12:00:00", help="Start date for products"
    )
    parser.add_argument("--n_jobs", type=int, default=4, help="Number of parallel jobs")
    parser.add_argument(
        "--log_level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO"
    )
    parser.add_argument(
        "--skip_extraction", action="store_true", help="Skip ECMWF extraction"
    )

    args = parser.parse_args()
    setup_logging(args.log_level)

    logger.info("=" * 60)
    logger.info("🚀 Starting dummy catalogue creation with ECMWF extraction")
    logger.info("=" * 60)

    catalogue_df = create_dummy_catalogue(
        date_start=args.date_start, step_deg=args.step_deg
    )

    if not args.skip_extraction:
        catalogue_df = extract_ecmwf_for_catalogue(
            catalogue_df, config_path=args.config_path, n_jobs=args.n_jobs, verbose=True
        )

    if args.output_catalogue:
        # Drop the temporary Shapely geometry column before saving,
        # PyArrow cannot serialize Shapely objects directly.
        # The data is already stored as WKT strings in 'polygon SLC'.
        cols_to_drop = [col for col in ["geometry"] if col in catalogue_df.columns]
        catalogue_df.drop(columns=cols_to_drop).to_parquet(args.output_catalogue)
        logger.info(f"✅ Saved catalogue to: {args.output_catalogue}")

    logger.info("\n🗺️ Creating maps...")
    plot_ecmwf_map(
        catalogue_df,
        args.output_png_dir,
        var_name="U10 ecmwf",
        cmap="RdBu_r",
        log_level=args.log_level,
    )
    plot_ecmwf_map(
        catalogue_df,
        args.output_png_dir,
        var_name="V10 ecmwf",
        cmap="RdBu_r",
        log_level=args.log_level,
    )
    plot_combined_map(catalogue_df, args.output_png_dir, log_level=args.log_level)

    logger.info("\n✅ All done!")


if __name__ == "__main__":
    main()
