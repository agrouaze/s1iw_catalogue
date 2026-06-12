"""Command-line interface for s1iw_catalogue."""

from pathlib import Path
from typing import Optional

import click


@click.group()
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to configuration file.")
@click.pass_context
def main(ctx: click.Context, config: Optional[Path]) -> None:
    """s1iw_catalogue – Exhaustive catalogue of Sentinel-1 IW SAFE products."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = config


@main.command()
@click.option("--output", "-o", required=True, type=click.Path(), help="Output .parquet file path.")
@click.pass_context
def create(ctx: click.Context, output: Path) -> None:
    """Create a brand new catalogue from scratch."""
    click.echo(f"Creating catalogue at {output}")


@main.command()
@click.option("--catalogue", "-c", required=True, type=click.Path(exists=True), help="Existing catalogue file.")
@click.option("--force-meteo", is_flag=True, help="Refresh meteorological columns even if already filled.")
@click.pass_context
def update(ctx: click.Context, catalogue: Path, force_meteo: bool) -> None:
    """Incrementally update the catalogue."""
    click.echo(f"Updating {catalogue}")


@main.command()
@click.option("--catalogue", "-c", required=True, type=click.Path(exists=True), help="Catalogue file.")
@click.option("--dataset", "-d", help="Filter statistics to a specific dataset.")
@click.option("--verbose", "-v", is_flag=True, help="Print detailed statistics.")
@click.option("--output", "-o", type=click.Path(), help="Export statistics to JSON file.")
@click.pass_context
def stats(ctx: click.Context, catalogue: Path, dataset: Optional[str], verbose: bool, output: Optional[Path]) -> None:
    """Print statistics about the catalogue."""
    click.echo(f"Stats for {catalogue}")


@main.command()
@click.option("--catalogue", "-c", required=True, type=click.Path(exists=True), help="Catalogue file.")
@click.option("--backup-dir", "-d", type=click.Path(), help="Directory to store backups.")
@click.pass_context
def backup(ctx: click.Context, catalogue: Path, backup_dir: Optional[Path]) -> None:
    """Create a timestamped backup of the catalogue."""
    click.echo(f"Backing up {catalogue}")


@main.command()
@click.option("--catalogue", "-c", required=True, type=click.Path(exists=True), help="Catalogue file.")
@click.option("--safe-name", "-s", required=True, help="Name of the SAFE product to query.")
@click.pass_context
def query(ctx: click.Context, catalogue: Path, safe_name: str) -> None:
    """Look up a SAFE by name and display its information."""
    click.echo(f"Querying {catalogue} for {safe_name}")


if __name__ == "__main__":
    main()