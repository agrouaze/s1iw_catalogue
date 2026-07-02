"""Command-line interface for s1iw_catalogue."""

from typing import Optional

import logging
from pathlib import Path

import click

from s1iw_catalogue.catalogue import S1IWCatalogue
from s1iw_catalogue.config import load_config
from s1iw_catalogue.stats import CatalogueStats

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


# =============================================================================
# MAIN GROUP
# =============================================================================
@click.group()
@click.option(
    "--config", "-c", type=click.Path(exists=True), help="Path to configuration file."
)
@click.pass_context
def main(ctx: click.Context, config: Path | None) -> None:
    """s1iw_catalogue – Exhaustive catalogue of Sentinel-1 IW SAFE products."""
    ctx.ensure_object(dict)
    cfg = load_config(config_path=config)
    ctx.obj["config"] = cfg
    ctx.obj["config_path"] = config


# =============================================================================
# COMMAND: create
# =============================================================================
@main.command()
@click.option(
    "--output",
    "-o",
    required=True,
    type=click.Path(),
    help="Output .parquet file path.",
)
@click.option(
    "--listing",
    "-l",
    help=(
        "Name of a single dataset/listing from the config file to use "
        "(e.g., ciaran2023). If omitted, all listings are used."
    ),
)
@click.pass_context
def create(ctx: click.Context, output: Path, listing: str | None) -> None:
    """
    Create a brand new catalogue from scratch.

    If --listing is provided, only that dataset is used; otherwise all
    listings from the config are processed.
    """
    cfg = ctx.obj["config"]
    config_path = ctx.obj.get("config_path")
    cat = S1IWCatalogue(catalogue_path=output, config=cfg, config_path=config_path)

    if listing:
        reference_listings = cfg.get("paths", {}).get("reference_listings", {})
        if listing not in reference_listings:
            click.echo(
                f"Error: Listing '{listing}' not found in configuration.", err=True
            )
            raise click.Abort()
        filtered_config = cfg.copy()
        filtered_config["paths"] = {
            "reference_listings": {listing: reference_listings[listing]}
        }
        cat = S1IWCatalogue(
            catalogue_path=output, config=filtered_config, config_path=config_path
        )

    cat.create(output_path=output)
    click.echo("Done.")


# =============================================================================
# COMMAND: update
# =============================================================================
@main.command()
@click.option(
    "--catalogue",
    "-c",
    required=True,
    type=click.Path(exists=True),
    help="Existing catalogue file.",
)
@click.option(
    "--force-meteo",
    is_flag=True,
    help="Refresh meteorological columns even if already filled.",
)
@click.pass_context
def update(ctx: click.Context, catalogue: Path, force_meteo: bool) -> None:
    """Incrementally update an existing catalogue."""
    cfg = ctx.obj["config"]
    config_path = ctx.obj.get("config_path")
    cat = S1IWCatalogue(catalogue_path=catalogue, config=cfg, config_path=config_path)
    click.echo(f"Updating {catalogue}...")
    cat.update(force_meteo_refresh=force_meteo)
    click.echo("Done.")


# =============================================================================
# COMMAND: stats
# =============================================================================
@main.command()
@click.option(
    "--catalogue",
    "-c",
    required=True,
    type=click.Path(exists=True),
    help="Catalogue file.",
)
@click.option("--dataset", "-d", help="Filter statistics to a specific dataset.")
@click.option("--verbose", "-v", is_flag=True, help="Print detailed statistics.")
@click.option(
    "--output", "-o", type=click.Path(), help="Export statistics to JSON file."
)
@click.pass_context
def stats(
    ctx: click.Context,
    catalogue: Path,
    dataset: str | None,
    verbose: bool,
    output: Path | None,
) -> None:
    """Print statistics about the catalogue."""
    import polars as pl

    df = pl.read_parquet(catalogue)

    if dataset:
        df = df.filter(pl.col("datasets").list.contains(dataset))
        if df.height == 0:
            click.echo(f"No products found for dataset '{dataset}'")
            return
        click.echo(f"Filtered to dataset '{dataset}' ({df.height} products)\n")

    stats_obj = CatalogueStats(df)

    if output:
        stats_obj.to_json(output)
        click.echo(f"Statistics written to {output}")
    else:
        click.echo(stats_obj.to_string())

        if verbose:
            click.echo("\n" + "-" * 60)
            click.echo("VERBOSE OUTPUT - Sample rows")
            click.echo("-" * 60)
            sample_cols = [
                "SAFE SLC",
                "SAFE GRD",
                "datasets",
                "polarization",
                "unit",
            ]
            sample_cols = [c for c in sample_cols if c in df.columns]
            click.echo(df.select(sample_cols).head(5))


# =============================================================================
# COMMAND: backup
# =============================================================================
@main.command()
@click.option(
    "--catalogue",
    "-c",
    required=True,
    type=click.Path(exists=True),
    help="Catalogue file.",
)
@click.option(
    "--backup-dir", "-d", type=click.Path(), help="Directory to store backups."
)
@click.pass_context
def backup(ctx: click.Context, catalogue: Path, backup_dir: Path | None) -> None:
    """Create a timestamped backup of the catalogue."""
    cfg = ctx.obj["config"]
    cat = S1IWCatalogue(catalogue_path=catalogue, config=cfg)
    backup_path = cat.backup(backup_dir=backup_dir)
    click.echo(f"Backup created: {backup_path}")


# =============================================================================
# COMMAND: query
# =============================================================================
@main.command()
@click.option(
    "--catalogue",
    "-c",
    required=True,
    type=click.Path(exists=True),
    help="Catalogue file.",
)
@click.option(
    "--safe-name", "-s", required=True, help="Name of the SAFE product to query."
)
@click.pass_context
def query(ctx: click.Context, catalogue: Path, safe_name: str) -> None:
    """Look up a SAFE by name and display its information."""
    cfg = ctx.obj["config"]
    cat = S1IWCatalogue(catalogue_path=catalogue, config=cfg)
    result = cat.query(safe_name)
    if result is None:
        click.echo(f"SAFE '{safe_name}' not found in catalogue.")
    else:
        click.echo("SAFE information:")
        for key, value in result.items():
            click.echo(f"  {key}: {value}")


# =============================================================================
# COMMAND: serve
# =============================================================================
@main.command()
@click.option("--host", default="127.0.0.1", help="Host to bind the web server to.")
@click.option("--port", default=8649, type=int, help="Port to bind the web server to.")
@click.option(
    "--catalogue",
    "-c",
    required=True,
    type=click.Path(exists=True),
    help="Catalogue .parquet file to serve.",
)
@click.option("--reload", is_flag=True, help="Enable auto-reload for development.")
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug logging for the web server.",
)
@click.pass_context
def serve(
    ctx: click.Context,
    host: str,
    port: int,
    catalogue: Path,
    reload: bool,
    debug: bool,
) -> None:
    """
    Launch the web interface to explore the catalogue.

    Dataset metadata (names and descriptions) is loaded from the config file
    if available via --config.
    """
    import os

    # Set debug logging if requested
    if debug:
        import logging
        logging.getLogger("s1iw_catalogue").setLevel(logging.DEBUG)
        logging.getLogger("s1iw_catalogue.web").setLevel(logging.DEBUG)
        logging.getLogger("s1iw_catalogue.catalogue").setLevel(logging.DEBUG)
        click.echo("🐛 Debug logging enabled")

    os.environ["S1IW_CATALOGUE_PATH"] = str(catalogue)

    config_path = ctx.obj.get("config_path")
    if config_path:
        os.environ["S1IW_CONFIG_PATH"] = str(config_path)
        click.echo(f"📁 Using config: {config_path}")
    else:
        click.echo("⚠️  No config path provided. Dataset metadata will be unavailable.")

    click.echo(f"🚀 Starting web server at http://{host}:{port}")
    click.echo(f"📁 Serving catalogue: {catalogue}")
    click.echo("📖 API docs available at /docs")

    import uvicorn

    from s1iw_catalogue.web.app import app

    uvicorn.run(
        "s1iw_catalogue.web.app:app",
        host=host,
        port=port,
        reload=reload,
    )


# =============================================================================
# COMMAND: merge
# =============================================================================
@main.command()
@click.argument(
    "catalogues",
    nargs=-1,
    required=True,
    type=click.Path(exists=True),
)
@click.option(
    "--output",
    "-o",
    required=True,
    type=click.Path(),
    help="Output merged .parquet file.",
)
@click.pass_context
def merge(ctx: click.Context, catalogues: tuple[Path], output: Path) -> None:
    """
    Merge multiple catalogues into a single file.

    CATALOGUES: list of input .parquet files to merge (at least 2).
    """
    if len(catalogues) < 2:
        click.echo("Error: At least two catalogues are required for merging.", err=True)
        raise click.Abort()
    cfg = ctx.obj["config"]
    config_path = ctx.obj.get("config_path")
    cat = S1IWCatalogue(catalogue_path=output, config=cfg, config_path=config_path)
    cat.merge(list(catalogues), output)
    click.echo(f"Merged {len(catalogues)} catalogues into {output}")


# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    main()