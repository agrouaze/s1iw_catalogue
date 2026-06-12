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

Build a single Parquet file with availability, dataset membership, meteorological enrichment, and acquisition geometry. Enables fast dashboards, product lookup, and spatial heatmaps.

</div>

## Overview

This tool creates and maintains a master Parquet file (`sentinel-1_exhaustive_IW_SAFE_working_material.parquet`) that answers:

- Which SAFE products (SLC, GRD, OCN) are available on Ifremer storage?
- Do they belong to internal datasets (`sarwave`, `scat`, etc.)?
- Are they colocalised with reference listings?
- What are the associated wave (WW3) and wind (ECMWF) parameters?
- What is the acquisition start date, geometry, orbit, and polarisation?

The file is updated **daily** via a workflow that uses:
- `cdse_match_product_type` for SLC↔GRD matching
- `s1ifr` to check local presence at Ifremer
- `familyprod` to derive A21, B17, OCN and dataset membership
- Optional ECMWF/WW3 enrichment

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

## Usage

### Build the exhaustive Parquet catalogue

```
from s1iw_catalogue.builder import build_catalogue

# Build with default settings (uses reference listings from config/)
build_catalogue(output_path="sentinel-1_exhaustive_IW_SAFE_working_material.parquet")
```

### Query the catalogue

```
import pandas as pd

df = pd.read_parquet("sentinel-1_exhaustive_IW_SAFE_working_material.parquet")

# Find a specific SAFE
safe_row = df[df["SAFE SLC"] == "S1A_IW_SLC__1SDV_20250101T123456_20250101T123523_012345_012345_0123"]

# Get all SAFE belonging to 'sarwave' dataset
sarwave_safes = df[df["dataset(s) d'appartenance"].apply(lambda x: "sarwave" in x)]
```

### Command-line interface (planned)

```
s1iw-catalogue build --ref-listings ./listings --output ./catalogue.parquet
s1iw-catalogue query --safe-name S1A_IW_GRD...
s1iw-catalogue heatmap --dataset sarwave --variable Hs --output map.png
```

## Features

### Core functionalities

- **Daily incremental update** of the Parquet catalogue.
- **SAFE deduplication** – merges information from multiple sources.
- **Presence tracking** for SLC, GRD, OCN, A21, B17 (local paths or NULL).
- **Dataset membership** as an array of strings.
- **Colocalisation** with any reference listing.
- **Enrichment** with WW3 (Hs, Tp) and ECMWF (U10, V10) – optional.
- **Geometry** – acquisition polygon (WKT) and start date.

### Development features

- Supports **Python 3.11+**.
- **No Poetry** – uses `pip` + `hatchling` for building.
- Codestyle with `black`, `isort`, `pyupgrade`.
- Pre-commit hooks.
- Type checks with `mypy`, docstring checks with `darglint`.
- Security checks with `safety` and `bandit`.
- Testing with `pytest` and coverage reporting.

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