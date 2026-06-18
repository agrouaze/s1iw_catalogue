"""Command-line interface for s1iw_catalogue."""

from pathlib import Path
from typing import Optional

import click
import polars as pl

from s1iw_catalogue.catalogue import S1IWCatalogue
from s1iw_catalogue.config import load_config
from s1iw_catalogue.stats import CatalogueStats


@click.group()
@click.option(
    "--config", "-c", type=click.Path(exists=True), help="Path to configuration file."
)
@click.pass_context
def main(ctx: click.Context, config: Optional[Path]) -> None:
    """s1iw_catalogue – Exhaustive catalogue of Sentinel-1 IW SAFE products."""
    ctx.ensure_object(dict)
    # Load configuration once and store in context
    cfg = load_config(config_path=config)
    ctx.obj["config"] = cfg


@main.command()
@click.option(
    "--output",
    "-o",
    required=True,
    type=click.Path(),
    help="Output .parquet file path.",
)
@click.pass_context
def create(ctx: click.Context, output: Path) -> None:
    """Create a brand new catalogue from scratch."""
    cfg = ctx.obj["config"]
    cat = S1IWCatalogue(catalogue_path=output, config=cfg)
    click.echo(f"Creating catalogue at {output}...")
    cat.create(output_path=output)
    click.echo("Done.")


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
    """Incrementally update the catalogue."""
    cfg = ctx.obj["config"]
    cat = S1IWCatalogue(catalogue_path=catalogue, config=cfg)
    click.echo(f"Updating {catalogue}...")
    cat.update(force_meteo_refresh=force_meteo)
    click.echo("Done.")


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
    dataset: Optional[str],
    verbose: bool,
    output: Optional[Path],
) -> None:
    """Print statistics about the catalogue."""
    import polars as pl

    df = pl.read_parquet(catalogue)

    if dataset:
        df = df.filter(pl.col("dataset(s) d'appartenance").list.contains(dataset))
        if df.height == 0:
            click.echo(f"No products found for dataset '{dataset}'")
            return
        click.echo(f"Filtered to dataset '{dataset}' ({df.height} products)\n")

    stats_obj = CatalogueStats(df)

    if output:
        stats_obj.to_json(output)
        click.echo(f"Statistics written to {output}")
    else:
        # Print the summary string
        click.echo(stats_obj.to_string())

        if verbose:
            click.echo("\n" + "-" * 60)
            click.echo("VERBOSE OUTPUT - Sample rows")
            click.echo("-" * 60)
            sample_cols = ["SAFE SLC", "SAFE GRD", "dataset(s) d'appartenance", "polarization", "unité"]
            sample_cols = [c for c in sample_cols if c in df.columns]
            click.echo(df.select(sample_cols).head(5))


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
def backup(ctx: click.Context, catalogue: Path, backup_dir: Optional[Path]) -> None:
    """Create a timestamped backup of the catalogue."""
    cfg = ctx.obj["config"]
    cat = S1IWCatalogue(catalogue_path=catalogue, config=cfg)
    backup_path = cat.backup(backup_dir=backup_dir)
    click.echo(f"Backup created: {backup_path}")


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


@main.command()
@click.option("--host", default="127.0.0.1", help="Host to bind the web server to.")
@click.option("--port", default=8649, type=int, help="Port to bind the web server to.")
@click.option("--catalogue", "-c", required=True, type=click.Path(exists=True), help="Catalogue .parquet file to serve.")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development.")
@click.pass_context
def serve(
    ctx: click.Context,
    host: str,
    port: int,
    catalogue: Path,
    reload: bool,
) -> None:
    """Launch web interface to explore the catalogue."""
    import os
    os.environ["S1IW_CATALOGUE_PATH"] = str(catalogue)
    
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


if __name__ == "__main__":
    main()