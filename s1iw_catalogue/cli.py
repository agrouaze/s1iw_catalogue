"""Command-line interface for s1iw_catalogue."""

from pathlib import Path
from typing import Optional

import click

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
    # Load catalogue DataFrame directly (no need for S1IWCatalogue instance)
    import polars as pl
    df = pl.read_parquet(catalogue)
    stats_obj = CatalogueStats(df)
    if output:
        stats_obj.to_json(output)
        click.echo(f"Statistics written to {output}")
    else:
        # Print a summary to console
        click.echo(f"Catalogue: {catalogue}")
        click.echo(f"Total entries: {stats_obj.total_count()}")
        counts = stats_obj.product_type_counts()
        click.echo(f"  SLC: {counts.get('SLC',0)}")
        click.echo(f"  GRD: {counts.get('GRD',0)}")
        click.echo(f"  OCN: {counts.get('OCN',0)}")
        # Optionally show dataset counts
        ds_counts = stats_obj.dataset_membership_counts()
        if ds_counts:
            click.echo("Dataset memberships:")
            for ds, cnt in ds_counts.items():
                click.echo(f"  {ds}: {cnt}")


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


if __name__ == "__main__":
    main()