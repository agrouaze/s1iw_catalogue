"""Lightweight CLI for web serving - no catalogue creation dependencies."""

import logging
import sys
from pathlib import Path

import click
import uvicorn


@click.command()
@click.option("--host", default="0.0.0.0", help="Host to bind")
@click.option("--port", default=8649, type=int, help="Port to bind")
@click.option(
    "--catalogue",
    required=True,
    type=click.Path(exists=True),
    help="Path to catalogue.parquet",
)
@click.option(
    "--config", required=True, type=click.Path(exists=True), help="Path to config.yml"
)
@click.option(
    "--verbose", is_flag=True, help="Enable debug logging (sets log level to DEBUG)"
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False),
    default="INFO",
    help="Set logging level (default: INFO)",
)
def main(host: str, port: int, catalogue: str, config: str, verbose: bool, log_level: str):
    """Serve the S1IW catalogue web interface."""
    # 1. Set up logging
    if verbose:
        log_level = "DEBUG"
    level = getattr(logging, log_level.upper())
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )

    # 2. Create the app (this triggers catalogue loading and any preprocessing)
    from s1iw_catalogue.web.app import create_app

    app = create_app(catalogue_path=Path(catalogue), config_path=Path(config))

    # 3. Start the server with the same log level
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level.lower(),
        access_log=True,
    )


if __name__ == "__main__":
    main()