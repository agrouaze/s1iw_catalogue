# s1iw_catalogue – Design Document

## 1. Objective

Build and maintain a single **Parquet** file that centralises, for each SAFE (Sentinel-1 IW product), information on availability, membership in internal datasets, meteorological enrichment, and location. This file must enable fast queries for:

- Monitoring dashboards (data usability percentages for SLC, GRD, OCN, A21, B17, …)
- SAFE name lookup (status and dataset membership of a product)
- Heatmap production (significant wave height, peak period, wind) per dataset

## 2. Parquet File Description

### 2.1 File Name
`sentinel-1_exhaustive_IW_SAFE_working_material.parquet`

### 2.2 Column Schema (exact, no additions)

| Column name | Type | Description |
|-------------|------|-------------|
| `SAFE SLC` | string | SAFE name when it is an SLC product (empty otherwise) |
| `SAFE GRD` | string | SAFE name when it is a GRD product (empty otherwise) |
| `SAFE OCN` | string | SAFE name when it is an OCN product (empty otherwise) |
| `presence SLC` | string | Local path or `NULL` indicating SLC presence on Ifremer storage |
| `presence GRD` | string | Local path or `NULL` for GRD |
| `presence OCN` | string | Local path or `NULL` for OCN |
| `presence L1B XSP A21` | string | Local path or `NULL` for derived product A21 (L1B XSP) |
| `presence L1C XSP B17` | string | Local path or `NULL` for derived product B17 (L1C XSP) |
| `dataset(s) d'appartenance` | string[] | List of internal datasets the SAFE belongs to (e.g., `["sarwave","scat"]`) |
| `Hs WW3` | float | Significant wave height (m) from WaveWatch III, interpolated to SAFE centroid |
| `Tp WW3` | float | Peak period (s) from WW3 |
| `U10 ecmwf` | float | Zonal wind at 10 m (m/s) from ECMWF (0.1° grid) |
| `v10 ecmwf` | float | Meridional wind at 10 m (m/s) from ECMWF |
| `start date SAFE` | timestamp | Acquisition start date (extracted from the populated SAFE column) |
| `horodating` | timestamp | Date and time when this row was **last updated** in the catalogue (system time) |
| `polygon of the acquisition from CDSE` | string | Ground footprint polygon (WKT format) as provided by Copernicus Data Space Ecosystem (CDSE) |
| `S3path from CDSE` | string | S3 path (or URL) of the product on CDSE |
| `polarization` | string | One of: `SDV`, `SSV`, `SDH`, `SSH` (Ifremer internal convention) |
| `unité` | string | Satellite identifier: `S1A`, `S1B`, `S1C`, `S1D` |

> **Note**:
> - One row corresponds to **a single unique SAFE** identified by one of the three fields `SAFE SLC`, `SAFE GRD` or `SAFE OCN` (the two others remain empty).
> - The `horodating` column tracks when the row was last modified, enabling incremental updates and monitoring of catalogue freshness.
> - The file is time‑partitioned by acquisition year/month to optimise queries.

## 3. Command-Line Interface (CLI)

The tool provides a command-line interface with several subcommands:

### 3.1 `catalog-iw --create`

Create a brand new `.parquet` catalogue from scratch.

```
catalog-iw --create --config /path/to/config.yml --output /path/to/catalogue.parquet
```

Behaviour:
- Reads reference listings (SLC/GRD/colocalisation) from configuration.
- Queries CDSE, `s1ifr`, `familyprod` for all products.
- Builds the Parquet file from zero.
- Sets `horodating` to current timestamp for all rows.
- Overwrites any existing file at the output path.

### 3.2 `catalog-iw --update`

Update the existing catalogue incrementally.

```
catalog-iw --update --catalogue /path/to/catalogue.parquet --config /path/to/config.yml
```

Behaviour:
- Reads existing catalogue.
- Identifies SAFE rows that need updates based on:
  - New products appearing in reference listings.
  - Changes in `presence` columns (new paths discovered).
  - New dataset memberships from `familyprod`.
  - Enrichment columns (`Hs WW3`, etc.) if previously empty.
- **Columns that already have a value are NOT overwritten** unless explicitly forced (e.g., `--force-meteo`).
- Only updates the `horodating` column for rows that actually changed.
- Appends new rows for previously unknown SAFE.

Update rules per column family:

| Column family | Update behaviour |
|---------------|------------------|
| `presence *` | Fill if empty; never overwrite an existing path |
| `dataset(s) d'appartenance` | Merge new datasets; preserve existing ones |
| `Hs WW3`, `Tp WW3`, `U10 ecmwf`, `v10 ecmwf` | Fill if empty; optional `--force-meteo` to refresh |
| `horodating` | Always set to current time when row is modified |
| `start date SAFE`, `polygon`, `S3path`, `polarization`, `unité` | Set once at creation; never updated |

### 3.3 `catalog-iw --stats`

Print statistics about the catalogue.

```
catalog-iw --stats --catalogue /path/to/catalogue.parquet [--dataset sarwave] [--verbose]
```

Output includes:
- Total number of SAFE entries.
- Count and percentage of SLC, GRD, OCN products.
- For each dataset (e.g., `sarwave`, `scat`):
  - Number of SAFE belonging to that dataset.
  - Percentage of complete presence (SLC/GRD/OCN/A21/B17 available).
- Latest ingested SAFE in **acquisition time** (`start date SAFE`).
- Latest ingested SAFE in **horodating time** (when last updated in catalogue).
- Global statistics per `unité` (S1A, S1B, etc.) and per `polarization`.
- Optional: export statistics as JSON (`--output stats.json`).

### 3.4 `catalog-iw --backup`

Save a timestamped copy of the current catalogue.

```
catalog-iw --backup --catalogue /path/to/catalogue.parquet [--backup-dir /path/to/backups]
```

Behaviour:
- Creates a copy named `catalogue_YYYYMMDD_HHMMSS.parquet` in the backup directory.
- Preserves the original file unchanged.
- Keeps only the last N backups (configurable, default 7).
- Useful before running `--update` or `--create` on a production catalogue.

### 3.5 `catalog-iw --config` (global option)

All commands accept a `--config` option to specify which configuration file to use.

```
catalog-iw --config /etc/s1iw/production.yml --create
```

If not provided, the tool looks for `config.yml` in the current working directory, then in `~/.config/s1iw_catalogue/config.yml`, then falls back to default settings.

## 4. Configuration System

### 4.1 Configuration Hierarchy

The tool uses a layered configuration system (higher priority overrides lower):

1. **Command-line arguments** (highest priority)
2. **Local configuration** (`localconfig.yml` – NOT versioned)
3. **Versioned configuration** (`config.yml` – committed to Git)
4. **Default built-in values** (lowest priority)

### 4.2 `config.yml` (versioned, shared across team)

```
# config.yml – Versioned configuration (commit to Git)

paths:
  reference_listings:
    slc: "/shared/listings/slc_reference.csv"
    grd: "/shared/listings/grd_reference.csv"
    coloc: "/shared/listings/colocalisation_listings.csv"
  output:
    catalogue: "/shared/catalogues/sentinel-1_exhaustive_IW_SAFE_working_material.parquet"
    backups: "/shared/catalogues/backups/"

sources:
  cdse:
    api_url: "https://dataspace.copernicus.eu"
    timeout_seconds: 300
    max_retries: 3
  s1ifr:
    endpoint: "https://ifremer-s1ifr.internal/api"
  familyprod:
    database_path: "/shared/familyprod/products.db"

enrichment:
  ecmwf:
    enabled: true
    grid_resolution: 0.1
    source: "https://ecmwf.ifremer.fr/data"
  ww3:
    enabled: false  # disabled by default (expensive)
    grid: "WW3_GLO_0p5"

update_rules:
  force_meteo_refresh: false  # default: only fill empty cells
  incremental_only: true       # true = never rebuild from scratch unless --create

backup:
  keep_last: 7                 # number of backups to retain
  compression: "snappy"

logging:
  level: "INFO"
  file: "/var/log/s1iw_catalogue.log"
```

### 4.3 `localconfig.yml` (NOT versioned, user/infrastructure specific)

```
# localconfig.yml – User-specific overrides (add to .gitignore)

paths:
  output:
    catalogue: "/home/agrouaze/scratch/test_catalogue.parquet"  # local test path

sources:
  s1ifr:
    endpoint: "http://localhost:8080/s1ifr"  # development instance

enrichment:
  ecmwf:
    enabled: false  # disable on laptop to save bandwidth

logging:
  level: "DEBUG"
```

### 4.4 Configuration Loading Logic

```
# Pseudo-code
def load_config(config_path=None):
    defaults = load_defaults()
    versioned = load_yaml("config.yml") if exists else {}
    local = load_yaml("localconfig.yml") if exists else {}
    cli_overrides = parse_cli_args()

    # Merge with priority: cli > local > versioned > defaults
    config = deep_merge(defaults, versioned)
    config = deep_merge(config, local)
    config = deep_merge(config, cli_overrides)
    return config
```

### 4.5 `.gitignore` updates

```
# Exclude local configuration
localconfig.yml

# Exclude generated version file (if using hatch-vcs)
s1iw_catalogue/_version.py

# Exclude catalogue files (if stored locally)
*.parquet
backups/
```

## 5. New Column: `horodating`

The `horodating` column (timestamp) is added to track **catalogue modification time** per row.

### 5.1 Purpose

- Know **when** a specific SAFE was last updated in the catalogue.
- Distinguish between acquisition date (`start date SAFE`) and catalogue ingestion date (`horodating`).
- Enable incremental `--update` logic: only process rows older than a certain threshold.
- Debugging: identify stale rows that may need manual refresh.

### 5.2 Update Rules

- **On `--create`**: set to current timestamp for all rows.
- **On `--update`**:
  - For rows that have **any column changed**: set `horodating = now()`.
  - For rows with no changes: leave `horodating` untouched.
- **Never** reset `horodating` to an older value.

### 5.3 Usage in `--stats`

```
catalog-iw --stats --catalogue catalogue.parquet
```

Example output:
```
Catalogue Statistics (as of 2026-06-12 14:30:22)
================================================
Total SAFE entries: 12,547
  - SLC: 4,201 (33.5%)
  - GRD: 8,010 (63.9%)
  - OCN: 336 (2.7%)

Dataset membership:
  - sarwave: 3,245 SAFE (25.9%)
  - scat: 1,892 SAFE (15.1%)

Latest acquisition (start date): 2026-06-11 23:45:12 (SAFE S1A_IW_GRD_...)
Latest catalogue update (horodating): 2026-06-12 14:30:15 (SAFE S1B_IW_SLC_...)

Rows never updated since creation: 23 (0.2%)
Rows older than 30 days (horodating): 156 (1.2%) - consider --update
```

## 6. Update Workflow (Revised)

The daily update workflow now respects the configuration and incremental update rules:

### 6.1 Daily cron / scheduled task

```
#!/bin/bash
# Daily update script

# Backup current catalogue
catalog-iw --backup --catalogue /shared/catalogues/main.parquet

# Incremental update
catalog-iw --update --catalogue /shared/catalogues/main.parquet --config /etc/s1iw/production.yml

# Generate stats and send to monitoring
catalog-iw --stats --catalogue /shared/catalogues/main.parquet --output /var/log/s1iw/daily_stats.json
```

### 6.2 Incremental update logic (detailed)

The `--update` command performs these steps:

1. **Load existing catalogue** into memory (using lazy loading with Dask or Polars).
2. **Read reference listings** from `config.yml`.
3. **Identify new SAFE** not present in catalogue → append rows.
4. **Identify existing SAFE** that may need updates based on:
   - New presence paths found on Ifremer storage.
   - New dataset assignments from `familyprod`.
   - Missing meteorological data (if `force_meteo_refresh` is true).
5. **For each candidate row**:
   - Query `s1ifr` for latest presence (if presence columns are empty).
   - Query `familyprod` for dataset membership (merge with existing).
   - Optionally refresh ECMWF/WW3 data.
   - If any column changed → update row and set `horodating = now()`.
6. **Write updated catalogue** (atomic: write to temp file, then rename).
7. **Log changes**: number of new rows, number of updated rows, number of unchanged rows.

## 7. Data Sources and External Dependencies

| Source / Tool | Role | Query frequency | Configurable |
|---------------|------|-----------------|--------------|
| `cdse_match_product_type` | SLC ↔ GRD matching | Per new SAFE | Endpoint, timeout |
| `s1ifr` | Ifremer storage presence | Daily (incremental) | Endpoint, retries |
| `familyprod` | Derived products (A21, B17, OCN) and datasets | Daily | Database path |
| Reference listings (local) | Define SAFE set to track | Per update | File paths in config |
| ECMWF / WW3 (API or files) | Meteorological variables | Optional, weekly | Enabled/disabled, grid |

## 8. Technical Requirements

- **Language**: Python 3.11+
- **Build system**: Hatchling + hatch-vcs (dynamic versioning from Git tags)
- **Key libraries**:
  - `polars` or `pandas` + `pyarrow` for Parquet I/O
  - `pyyaml` for configuration
  - `click` or `argparse` for CLI
  - `s1ifr`, `cdse`, `familyprod` as internal dependencies
- **Parquet compression**: `snappy` or `zstd`
- **Parallelism**: Use Ifremer HPC for heavy processing (no resource constraints)
- **Scheduling**: Cron or Airflow for daily `--update`
- **Storage**: Sufficient disk space for catalogue and backups (tens of GB eventually)

## 9. Main Use Cases

1. **Monitoring dashboard**
   - Aggregate presence ratios (SLC available? GRD available? A21 generated?)
   - Track dataflow progression over acquisition time and horodating time

2. **SAFE name lookup page**
   - Enter product name (SLC, GRD, or OCN)
   - Display status of each column (`presence`, `dataset`, meteorological data, horodating)

3. **Spatio‑temporal heatmaps**
   - For a given dataset (e.g., `sarwave`), produce maps of `Hs WW3` or `U10` using centroids derived from polygons.

4. **Data quality monitoring**
   - Use `--stats` to detect stale rows (old `horodating`) or missing enrichments.

## 10. Points of Vigilance

- **SLC ↔ GRD matching**: Not always one‑to‑one. One SLC may produce several GRDs (temporal splitting). The business rule must be explicit in the code.
- **`horodating` column**: Essential for incremental updates but adds storage overhead (a few bytes per row). Acceptable.
- **Configuration security**: `localconfig.yml` may contain credentials. Add to `.gitignore`.
- **Atomic updates**: Always write to a temporary file before renaming to avoid corrupting the catalogue if the update fails mid‑way.
- **Backup retention**: Keep old backups to allow manual recovery. Default 7 days.
- **Performance of `--stats`**: On a large catalogue, computing percentages in real time may be slow. Consider caching statistics or using Parquet metadata.
- **ECMWF/WW3 optional**: If too heavy, disable in `config.yml` and run separately.

## 11. Future Enhancements (Not in Scope for v1)

- `catalog-iw --diff` – compare two catalogues and show changes.
- `catalog-iw --export` – export to CSV, GeoJSON, or Zarr.
- `catalog-iw --watch` – daemon mode that watches for new products and updates in real time.
- Web API (FastAPI) wrapper around the catalogue for remote queries.
- Integration with `dask` for parallel processing on HPC.

## 12. Next Steps

1. Implement configuration loader with `localconfig.yml` override.
2. Implement `--create` command (build from scratch).
3. Implement `--update` command with incremental logic and `horodating`.
4. Implement `--stats` command with all metrics.
5. Implement `--backup` command.
6. Add `horodating` column to the schema.
7. Write tests for each CLI command.
8. Deploy daily cron job with `--backup` and `--update`.

---

*Document approved – schema and CLI design frozen for v1 implementation.*
