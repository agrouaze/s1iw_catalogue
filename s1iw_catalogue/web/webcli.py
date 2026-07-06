"""Lightweight CLI for web serving - no catalogue creation dependencies."""

import click


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
def main(host: str, port: int, catalogue: str, config: str):
    """Serve the S1IW catalogue web interface."""
    from pathlib import Path

    import uvicorn

    from s1iw_catalogue.web.app import create_app

    app = create_app(catalogue_path=Path(catalogue), config_path=Path(config))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
