# s1iw_catalogue

<div align="center">

[![Build status](https://github.com/agrouaze/s1iw_catalogue/workflows/build/badge.svg?branch=master&event=push)](https://github.com/agrouaze/s1iw_catalogue/actions?query=workflow%3Abuild)
[![Python Version](https://img.shields.io/pypi/pyversions/s1iw_catalogue.svg)](https://pypi.org/project/s1iw_catalogue/)
[![Dependencies Status](https://img.shields.io/badge/dependencies-up%20to%20date-brightgreen.svg)](https://github.com/agrouaze/s1iw_catalogue/pulls?utf8=%E2%9C%93&q=is%3Apr%20author%3Aapp%2Fdependabot)

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Security: bandit](https://img.shields.io/badge/security-bandit-green.svg)](https://github.com/PyCQA/bandit)
[![Pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/agrouaze/s1iw_catalogue/blob/master/.pre-commit-config.yaml)
[![Semantic Versions](https://img.shields.io/badge/%20%20%F0%9F%93%A6%F0%9F%9A%80-semantic--versions-e10079.svg)](https://github.com/agrouaze/s1iw_catalogue/releases)
[![License](https://img.shields.io/github/license/agrouaze/s1iw_catalogue)](https://github.com/agrouaze/s1iw_catalogue/blob/master/LICENSE)
![Coverage Report](assets/images/coverage.svg)

**s1iw_catalogue** – Exhaustive catalogue of Sentinel‑1 IW SAFE products for Ifremer.

Build a single Parquet file with availability, dataset membership, category, meteorological enrichment, and acquisition geometry. Enables fast dashboards, product lookup, spatial heatmaps, and catalogue merging.

</div>

## Overview

This tool creates and maintains a master Parquet file (`sentinel-1_exhaustive_IW_SAFE_working_material.parquet`) that answers:

- Which SAFE products (SLC, GRD, OCN) are available on Ifremer storage?
- Do they belong to internal datasets (`ciaran2023`, `jolina26`, etc.)?
- What is their dataset category (`train`, `val`, `test`, `case-study`)?
- Are they colocalised with reference listings?
- What are the associated wave (WW3) and wind (ECMWF) parameters?
- What is the acquisition start date, geometry, orbit, and polarisation?

The file is updated **daily** via a workflow that uses:
- `cdse_match_product_type` for SLC↔GRD matching
- `s1ifr` to check local presence at Ifremer
- `familyprod` to derive A21, B17, OCN and dataset membership
- Optional ECMWF/WW3 enrichment

## Features

### Core functionalities

- **Create** – Build a catalogue from listing files with dataset metadata.
- **Update** – Incrementally update an existing catalogue with new listings.
- **Merge** – Combine multiple catalogues into one (parallel processing on HPC).
- **Stats** – Generate statistics and completeness reports.
- **Serve** – Launch a web interface for visual exploration (FastAPI + Plotly).
- **Query** – Look up SAFE products by name.
- **Backup** – Create timestamped backups of the catalogue.
- **Dataset categories** – Assign `undefined`, `train`, `val`, `test`, `case-study` with priority hierarchy.
- **Conflict reporting** – Track dataset category conflicts in a separate file.

### Column schema (key columns)

| Column | Description |
|--------|-------------|
| `SAFE SLC` | SAFE name for SLC product |
| `SAFE GRD` | SAFE name for GRD product |
| `SAFE OCN` | SAFE name for OCN product (or `"NOT_FOUND"`) |
| `PATH SLC` | Full path to SLC on Ifremer storage |
| `PATH GRD` | Full path to GRD on Ifremer storage |
| `PATH OCN` | Full path to OCN on Ifremer storage |
| `PATH L1B XSP A21` | Full path to L1B XSP A21 product |
| `PATH L1C XSP B17` | Full path to L1C XSP B17 product |
| `datasets` | List of dataset names (e.g., `["ciaran2023"]`) |
| `category` | Dataset category: `undefined`, `train`, `val`, `test`, `case-study` |
| `unit` | Satellite identifier: `S1A`, `S1B`, `S1C`, `S1D` |
| `start date SAFE` | Acquisition start date |
| `horodating` | Last catalogue update timestamp |
| `polygon SLC` / `polygon GRD` | Footprint polygon (WKT) |
| `S3path SLC` / `S3path GRD` | S3 path on CDSE |

## Configuration

The tool uses a YAML configuration file. Example:

```
paths:
  reference_listings:
    ciaran2023:
      path: "/path/to/listing.txt"
      type: "slc"
      description: "Storm Ciaran over Europe"
      category: "case-study"
    jolina26:
      path: "/path/to/grd_listing.txt"
      type: "grd"
      description: "Medicane Jolina"
      category: "case-study"
  output:
    catalogue: "/path/to/catalogue.parquet"
s1ifr-config-file: "/path/to/s1ifr/config.yml"
cdse_cache_dir: "/path/to/cache"
product_versions:
  l1b: ["A21", "A23"]
  l1c: ["B17", "B21"]
```

## Command-Line Interface

### Create a catalogue

```
catalog-iw --config config.yml create --output catalogue.parquet
```

Create a catalogue for a single listing (useful for parallel HPC processing):

```
catalog-iw --config config.yml create --output cat_ciaran.parquet --listing ciaran2023
```

### Update an existing catalogue

```
catalog-iw --config config.yml update --catalogue catalogue.parquet
```

### Merge multiple catalogues

```
catalog-iw --config config.yml merge cat1.parquet cat2.parquet --output merged.parquet
```

### Generate statistics

```
catalog-iw --config config.yml stats --catalogue catalogue.parquet
```

Filter by dataset:

```
catalog-iw --config config.yml stats --catalogue catalogue.parquet --dataset ciaran2023
```

Export to JSON:

```
catalog-iw --config config.yml stats --catalogue catalogue.parquet --output stats.json
```

### Launch web interface

```
catalog-iw --config config.yml serve --catalogue catalogue.parquet
```

Options:
- `--host` (default: `127.0.0.1`)
- `--port` (default: `8649`)
- `--reload` (development mode)

### Backup the catalogue

```
catalog-iw --config config.yml backup --catalogue catalogue.parquet
```

### Query a SAFE product

```
catalog-iw --config config.yml query --catalogue catalogue.parquet --safe-name S1A_IW_SLC_...
```

## Very first steps

### Initialize your code

1. Clone the repository and go inside:

```
git clone https://github.com/agrouaze/s1iw_catalogue.git
cd s1iw_catalogue
```

2. Create a virtual environment (optional but recommended):

```
python -m venv venv
source venv/bin/activate  # on Windows: venv\Scripts\activate
```

3. Install the package with development dependencies:

```
make install
```

This runs `pip install -e .[dev]` and also installs `mypy` stub types.

4. Install pre-commit hooks:

```
make pre-commit-install
```

5. Run codestyle formatting:

```
make codestyle
```

6. Upload initial code to GitHub (if you haven't already):

```
git add .
git commit -m ":tada: Initial commit"
git branch -M main
git remote add origin https://github.com/agrouaze/s1iw_catalogue.git
git push -u origin main
```

### Set up bots

- [Dependabot](https://docs.github.com/en/github/administering-a-repository/enabling-and-disabling-version-updates#enabling-github-dependabot-version-updates) for keeping dependencies up to date.
- [Stale bot](https://github.com/apps/stale) for automatic issue closing.

## Installation

You can install the package directly from GitHub or PyPI (once published).

```
pip install git+https://github.com/agrouaze/s1iw_catalogue.git
```

Or after publishing:

```
pip install s1iw_catalogue
```

**Note**: The package requires Python 3.11 or higher. It depends on `s1ifr` which is fetched from Ifremer's private PyPI index (configured automatically in `pyproject.toml`).

## Python API Usage

### Build the exhaustive Parquet catalogue

```
from s1iw_catalogue.catalogue import S1IWCatalogue

cat = S1IWCatalogue("catalogue.parquet", config="config.yml")
cat.create()
```

### Query the catalogue

```
import polars as pl

df = pl.read_parquet("catalogue.parquet")

# Find a specific SAFE
safe_row = df.filter(pl.col("SAFE SLC") == "S1A_IW_SLC__...")

# Get all SAFE belonging to a dataset
dataset_safes = df.filter(pl.col("datasets").list.contains("ciaran2023"))

# Get statistics
stats = cat.stats()
print(stats["total_count"])
```

## Makefile usage

The [`Makefile`](https://github.com/agrouaze/s1iw_catalogue/blob/master/Makefile) provides convenient commands.

<details>
<summary>1. Install dependencies</summary>

```
make install
```

Installs the package in editable mode with all dev dependencies.

</details>

<details>
<summary>2. Pre-commit hooks</summary>

```
make pre-commit-install
```

</details>

<details>
<summary>3. Codestyle</summary>

```
make codestyle          # formats code with pyupgrade, isort, black
make check-codestyle    # checks only, no changes
```

</details>

<details>
<summary>4. Type checks</summary>

```
make mypy
```

</details>

<details>
<summary>5. Tests with coverage</summary>

```
make test
```

Generates an HTML coverage report and a badge.

</details>

<details>
<summary>6. Security checks</summary>

```
make check-safety
```

Runs `pip check`, `safety`, and `bandit`.

</details>

<details>
<summary>7. All linters in one</summary>

```
make lint
```

Equivalent to `make test && make check-codestyle && make mypy && make check-safety`.

</details>

<details>
<summary>8. Docker</summary>

```
make docker-build       # builds Docker image (default tag latest)
make docker-remove      # removes the image
```

See [`docker/README.md`](docker/README.md) for details.

</details>

<details>
<summary>9. Cleanup</summary>

```
make cleanup            # removes pycache, .DS_Store, .mypy_cache, .pytest_cache, build/
```

</details>

## Releases

We follow [Semantic Versions](https://semver.org/).  
See [GitHub Releases](https://github.com/agrouaze/s1iw_catalogue/releases) for changelog.

## License

This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.

## Citation

```
@misc{s1iw_catalogue,
  author = {lops-wave},
  title = {s1iw_catalogue – exhaustive Sentinel-1 IW SAFE catalogue for Ifremer},
  year = {2026},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/agrouaze/s1iw_catalogue}}
}
```

## Credits

This project was generated with [`python-package-template`](https://github.com/TezRomacH/python-package-template) and adapted for `s1iw_catalogue`.