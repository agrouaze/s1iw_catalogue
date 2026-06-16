# s1iw_catalogue – Design Document

## 1. Objective

Build and maintain a single **Parquet** file that centralises, for each SAFE (Sentinel-1 IW product), information on availability, membership in internal datasets, meteorological enrichment, and location. This file must enable fast queries for:

- Monitoring dashboards (data usability percentages for SLC, GRD, OCN, A21, B17, …)
- SAFE name lookup (status and dataset membership of a product)
- Heatmap production (significant wave height, peak period, wind) per dataset

## 2. Parquet File Description

### 2.1 File Name
`sentinel-1_exhaustive_IW_SAFE_working_material.parquet`

### 2.2 Column Schema

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
| `dataset(s) d'appartenance` | string[] | List of dataset names the SAFE belongs to (e.g., `["hibou2", "zebra"]`). Assigned at build time from listing file names. |
| `Hs WW3` | float | Significant wave height (m) from WaveWatch III, interpolated to SAFE centroid |
| `Tp WW3` | float | Peak period (s) from WW3 |
| `U10 ecmwf` | float | Zonal wind at 10 m (m/s) from ECMWF (0.1° grid) |
| `v10 ecmwf` | float | Meridional wind at 10 m (m/s) from ECMWF |
| `start date SAFE` | timestamp | Acquisition start date (extracted from the SAFE name) |
| `horodating` | timestamp | Date and time when this row was **last updated** in the catalogue (system time) |
| `polygon SLC` | string | Ground footprint polygon (WKT format) for the SLC product from CDSE |
| `polygon GRD` | string | Ground footprint polygon (WKT format) for the GRD product from CDSE |
| `S3path SLC` | string | S3 path (or URL) of the SLC product on CDSE |
| `S3path GRD` | string | S3 path (or URL) of the GRD product on CDSE |
| `polarization` | string | One of: `SDV`, `SSV`, `SDH`, `SSH` (Ifremer internal convention) |
| `unité` | string | Satellite identifier: `S1A`, `S1B`, `S1C`, `S1D` |

> **Note**:
> - One row corresponds to **a single unique SAFE** identified by one of the three fields `SAFE SLC`, `SAFE GRD` or `SAFE OCN` (the two others remain empty).
> - The `horodating` column tracks when the row was last modified, enabling incremental updates and monitoring of catalogue freshness.
> - Polygon and S3path columns are split into SLC and GRD variants because footprints and storage paths differ between product types.
> - `dataset(s) d'appartenance` is populated at build time directly from the configuration structure (dataset names from listing file keys).

## 3. Core Logic: The Build and Link Workflow

The core of the library is the `link_slc_grd()` method in `CatalogueUpdater`. It orchestrates a multi-step pipeline to transform raw listings into a fully linked and enriched catalogue.

### 3.1 Overview of the `link_slc_grd()` Pipeline

The method executes the following steps in order:

1. **Build from listings** (`build_from_listings`)
   - Reads SLC and GRD listings from the configuration.
   - Each listing file is associated with a dataset name (e.g., `hibou2`, `castor5`, `zebra`).
   - Creates initial DataFrame with one row per SAFE product.
   - Populates `dataset(s) d'appartenance` with the dataset name(s) from the listing(s).
   - Sets placeholder `None` values for all other columns.

2. **Local SLC-GRD matching** (`_local_link_slc_grd`)
   - Identifies GRD rows that don't have an SLC linked yet.
   - Uses `data_take_id` (orbit pattern) + mission + polarization to find matches.
   - Within each match group, finds the SLC with closest start time (±5 seconds).
   - Fills `SAFE SLC` in GRD rows and `SAFE GRD` in SLC rows.

3. **CDSE fallback for orphans** (`_cdse_fallback_link`)
   - Finds remaining orphans: GRD without SLC, or SLC without GRD.
   - Queries CDSE using `cdsodatacli.match_s1_product_types.find_product_for_safe`.
   - Links the missing counterpart when found.

4. **Merge linked rows** (`_merge_linked_rows`)
   - After linking, there can be two rows for the same (SLC, GRD) pair.
   - Merges them into a single row.
   - Dataset arrays are combined (UNION).
   - Meteorological columns take first non-null value.
   - `horodating` takes the most recent timestamp.
   - Splits polygon and S3path columns into SLC/GRD variants.

5. **Fetch polygons and S3 paths** (`_update_polygons_and_s3paths`)
   - Queries CDSE using `cdsodatacli.query.fetch_data`.
   - Only fetches for products missing polygon or S3path information.
   - Uses exact start/end dates extracted from SAFE names.

6. **Check presence on Ifremer storage** (`_update_presence_columns`)
   - Uses `s1ifr.get_path_from_base_safe` to check if products exist.
   - Checks all configured archives (datawork, scale, etc.) sequentially.
   - Stores the full path if found, otherwise `NULL`.

### 3.2 Visual Pipeline Flow

$$$
Raw Listings (SLC + GRD)
        │
        ▼
┌─────────────────────────┐
│ build_from_listings()   │  ← Dataset names assigned here
│  - Read SLC listings    │
│  - Read GRD listings    │
│  - Assign datasets      │
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│ _local_link_slc_grd()   │  ← Local matching (fast, no API)
│  - Match by data_take   │
│  - Time window ±5s      │
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│ _cdse_fallback_link()   │  ← CDSE API for orphans
│  - GRD orphans → SLC    │
│  - SLC orphans → GRD    │
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│ _merge_linked_rows()    │  ← Merge pairs into one row
│  - Union datasets       │
│  - Split poly/S3path    │
│  - Most recent horodate │
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│ _update_polygons...()   │  ← CDSE for footprints
│  - Get WKT polygons     │
│  - Get S3 paths         │
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│ _update_presence...()   │  ← Ifremer storage check
│  - Check datawork/scale │
│  - Store full paths     │
└─────────────────────────┘
        │
        ▼
   Final Catalogue
$$$

## 4. Command-Line Interface (CLI)

The tool provides a command-line interface with several subcommands:

### 4.1 `catalog-iw --create`

Create a brand new `.parquet` catalogue from scratch.

$$$
catalog-iw --create --config /path/to/config.yml --output /path/to/catalogue.parquet
$$$

Behaviour:
- Reads reference listings (SLC/GRD) from configuration.
- Dataset names are taken from the listing file keys in the config.
- Executes the full pipeline (all 6 steps described above).
- Sets `horodating` to current timestamp for all rows.
- Overwrites any existing file at the output path.

### 4.2 `catalog-iw --update`

Update the existing catalogue incrementally.

$$$
catalog-iw --update --catalogue /path/to/catalogue.parquet --config /path/to/config.yml
$$$

Behaviour:
- Reads existing catalogue.
- Identifies SAFE rows that need updates based on:
  - New products appearing in reference listings.
  - Changes in `presence` columns (new paths discovered).
  - Missing enrichment columns.
- **Columns that already have a value are NOT overwritten** unless explicitly forced.
- Only updates the `horodating` column for rows that actually changed.
- Appends new rows for previously unknown SAFE.

Update rules per column family:

| Column family | Update behaviour |
|---------------|------------------|
| `presence *` | Fill if empty; never overwrite an existing path |
| `dataset(s) d'appartenance` | Merge new datasets; preserve existing ones |
| `Hs WW3`, `Tp WW3`, `U10 ecmwf`, `v10 ecmwf` | Fill if empty; optional `--force-meteo` to refresh |
| `horodating` | Always set to current time when row is modified |
| `start date SAFE`, `polygon SLC/GRD`, `S3path SLC/GRD`, `polarization`, `unité` | Set once at creation; never updated |

### 4.3 `catalog-iw --stats`

Print statistics about the catalogue.

$$$
catalog-iw --stats --catalogue /path/to/catalogue.parquet [--dataset sarwave] [--verbose]
$$$

Output includes:
- Total number of SAFE entries.
- Count and percentage of SLC, GRD, OCN products.
- For each dataset (e.g., `hibou2`, `zebra`):
  - Number of SAFE belonging to that dataset.
  - Percentage of complete presence (SLC/GRD available).
- Latest ingested SAFE in **acquisition time** (`start date SAFE`).
- Latest ingested SAFE in **horodating time** (when last updated in catalogue).
- Global statistics per `unité` (S1A, S1B, etc.) and per `polarization`.
- Optional: export statistics as JSON (`--output stats.json`).

### 4.4 `catalog-iw --backup`

Save a timestamped copy of the current catalogue.

$$$
catalog-iw --backup --catalogue /path/to/catalogue.parquet [--backup-dir /path/to/backups]
$$$

Behaviour:
- Creates a copy named `catalogue_YYYYMMDD_HHMMSS.parquet` in the backup directory.
- Preserves the original file unchanged.
- Keeps only the last N backups (configurable, default 7).
- Useful before running `--update` or `--create` on a production catalogue.

### 4.5 `catalog-iw --config` (global option)

All commands accept a `--config` option to specify which configuration file to use.

$$$
catalog-iw --config /etc/s1iw/production.yml --create
$$$

If not provided, the tool looks for `config.yml` in the current working directory, then in `~/.config/s1iw_catalogue/config.yml`, then falls back to default settings.

## 5. Configuration System

### 5.1 Configuration Hierarchy

The tool uses a layered configuration system (higher priority overrides lower):

1. **Command-line arguments** (highest priority)
2. **Local configuration** (`localconfig.yml` – NOT versioned)
3. **Versioned configuration** (`config.yml` – committed to Git)
4. **Default built-in values** (lowest priority)

### 5.2 `config.yml` (versioned, shared across team)

$$$
# config.yml – Versioned configuration (commit to Git)

paths:
  reference_listings:
    slc:
      hibou2: "/shared/listings/slc_hibou2.csv"
      castor5: "/shared/listings/slc_castor5.csv"
    grd:
      zebra: "/shared/listings/grd_zebra.csv"
  output:
    catalogue: "/shared/catalogues/sentinel-1_exhaustive_IW_SAFE_working_material.parquet"
    backups: "/shared/catalogues/backups/"

sources:
  cdse:
    api_url: "https://dataspace.copernicus.eu"
    timeout_seconds: 300
    max_retries: 3
  s1ifr:
    config_file: "/etc/s1ifr/config.yml"
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
$$$

### 5.3 `localconfig.yml` (NOT versioned, user/infrastructure specific)

$$$
# localconfig.yml – User-specific overrides (add to .gitignore)

paths:
  output:
    catalogue: "/home/agrouaze/scratch/test_catalogue.parquet"  # local test path

sources:
  s1ifr:
    config_file: "/home/agrouaze/git/s1ifr/s1ifr/localconfig.yml"

enrichment:
  ecmwf:
    enabled: false  # disable on laptop to save bandwidth

logging:
  level: "DEBUG"
$$$

### 5.4 Configuration Loading Logic

$$$
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
$$$

### 5.5 `.gitignore` updates

$$$
# Exclude local configuration
localconfig.yml

# Exclude generated version file (if using hatch-vcs)
s1iw_catalogue/_version.py

# Exclude catalogue files (if stored locally)
*.parquet
backups/
$$$

## 6. New Column: `horodating`

The `horodating` column (timestamp) tracks **catalogue modification time** per row.

### 6.1 Purpose

- Know **when** a specific SAFE was last updated in the catalogue.
- Distinguish between acquisition date (`start date SAFE`) and catalogue ingestion date (`horodating`).
- Enable incremental `--update` logic: only process rows older than a certain threshold.
- Debugging: identify stale rows that may need manual refresh.

### 6.2 Update Rules

- **On `--create`**: set to current timestamp for all rows.
- **On `--update`**:
  - For rows that have **any column changed**: set `horodating = now()`.
  - For rows with no changes: leave `horodating` untouched.
- **Never** reset `horodating` to an older value.

### 6.3 Usage in `--stats`

$$$
catalog-iw --stats --catalogue catalogue.parquet
$$$

Example output:
$$$
Catalogue Statistics (as of 2026-06-12 14:30:22)
================================================
Total SAFE entries: 12,547
  - SLC: 4,201 (33.5%)
  - GRD: 8,010 (63.9%)
  - OCN: 336 (2.7%)

Dataset membership:
  - hibou2: 3,245 SAFE (25.9%)
  - zebra: 1,892 SAFE (15.1%)

Latest acquisition (start date): 2026-06-11 23:45:12 (SAFE S1A_IW_GRD_...)
Latest catalogue update (horodating): 2026-06-12 14:30:15 (SAFE S1B_IW_SLC_...)

Rows never updated since creation: 23 (0.2%)
Rows older than 30 days (horodating): 156 (1.2%) - consider --update
$$$

## 7. Update Workflow (Revised)

The daily update workflow respects the configuration and incremental update rules:

### 7.1 Daily cron / scheduled task

$$$
#!/bin/bash
# Daily update script

# Backup current catalogue
catalog-iw --backup --catalogue /shared/catalogues/main.parquet

# Incremental update
catalog-iw --update --catalogue /shared/catalogues/main.parquet --config /etc/s1iw/production.yml

# Generate stats and send to monitoring
catalog-iw --stats --catalogue /shared/catalogues/main.parquet --output /var/log/s1iw/daily_stats.json
$$$

### 7.2 Incremental update logic (detailed)

The `--update` command performs these steps:

1. **Load existing catalogue** into memory (using Polars for efficient Parquet I/O).
2. **Read reference listings** from `config.yml` to identify new products.
3. **Identify new SAFE** not present in catalogue → append rows.
4. **Identify existing SAFE** that may need updates based on:
   - New presence paths found on Ifremer storage.
   - Missing polygon/S3path information.
   - Missing meteorological data (if `force_meteo_refresh` is true).
5. **For each candidate row**:
   - Query `s1ifr` for latest presence (if presence columns are empty).
   - Query CDSE for polygon and S3path (if missing).
   - Optionally refresh ECMWF/WW3 data.
   - If any column changed → update row and set `horodating = now()`.
6. **Write updated catalogue** (atomic: write to temp file, then rename).
7. **Log changes**: number of new rows, number of updated rows, number of unchanged rows.

## 8. Data Sources and External Dependencies

| Source / Tool | Role | Query frequency | Configurable |
|---------------|------|-----------------|--------------|
| `cdsodatacli.scripts.match_s1_product_types` | SLC ↔ GRD matching for orphans | Per new SAFE | Endpoint, timeout |
| `cdsodatacli.query.fetch_data` | Polygon and S3path retrieval | Once per product (if missing) | Endpoint, timeout |
| `s1ifr.get_path_from_base_safe` | Ifremer storage presence | Once per product (if missing) | Config file, archives |
| Reference listings (local) | Define SAFE set to track | Per update | File paths in config |
| ECMWF / WW3 (API or files) | Meteorological variables | Optional, weekly | Enabled/disabled, grid |
| `familyprod` | Derived products (A21, B17) | Future enhancement | Database path |

## 9. Technical Requirements

- **Language**: Python 3.11+
- **Build system**: Hatchling + hatch-vcs (dynamic versioning from Git tags)
- **Key libraries**:
  - `polars` for Parquet I/O and data manipulation
  - `pyyaml` for configuration
  - `click` for CLI
  - `s1ifr`, `cdsodatacli` as internal dependencies
- **Parquet compression**: `snappy`
- **Parallelism**: Use Ifremer HPC for heavy processing (no resource constraints)
- **Scheduling**: Cron or Airflow for daily `--update`
- **Storage**: Sufficient disk space for catalogue and backups (tens of GB eventually)

## 10. Main Use Cases

1. **Monitoring dashboard**
   - Aggregate presence ratios (SLC available? GRD available? A21 generated?)
   - Track dataflow progression over acquisition time and horodating time

2. **SAFE name lookup page**
   - Enter product name (SLC, GRD, or OCN)
   - Display status of each column (`presence`, `dataset`, meteorological data, horodating)

3. **Spatio‑temporal heatmaps**
   - For a given dataset (e.g., `hibou2`), produce maps of `Hs WW3` or `U10` using centroids derived from polygons.

4. **Data quality monitoring**
   - Use `--stats` to detect stale rows (old `horodating`) or missing enrichments.

## 11. Points of Vigilance

- **SLC ↔ GRD matching**: Local matching uses `data_take_id` + mission + polarization + time window (±5s). CDSE fallback handles cases where local matching fails.
- **`horodating` column**: Essential for incremental updates but adds storage overhead (a few bytes per row). Acceptable.
- **Configuration security**: `localconfig.yml` may contain credentials. Add to `.gitignore`.
- **Atomic updates**: Always write to a temporary file before renaming to avoid corrupting the catalogue if the update fails mid‑way.
- **Backup retention**: Keep old backups to allow manual recovery. Default 7 days.
- **Performance of `--stats`**: On a large catalogue, computing percentages in real time may be slow. Consider caching statistics or using Parquet metadata.
- **ECMWF/WW3 optional**: If too heavy, disable in `config.yml` and run separately.
- **Polygon/S3path columns**: Split into SLC and GRD variants to preserve product-specific information.
- **Dataset membership**: Assigned at build time from listing file names, not updated later.

## 12. Future Enhancements (Not in Scope for v1)

- `catalog-iw --diff` – compare two catalogues and show changes.
- `catalog-iw --export` – export to CSV, GeoJSON, or Zarr.
- `catalog-iw --watch` – daemon mode that watches for new products and updates in real time.
- Web API (FastAPI) wrapper around the catalogue for remote queries.
- Integration with `dask` for parallel processing on HPC.
- Derived product tracking (A21, B17) using `familyprod`.
- Meteorological enrichment (ECMWF/WW3).

## 13. Implementation Status

| Feature | Status |
|---------|--------|
| Configuration loader | ✅ Implemented |
| `--create` command | ✅ Implemented |
| Local SLC-GRD matching | ✅ Implemented |
| CDSE fallback matching | ✅ Implemented |
| Merging linked rows | ✅ Implemented |
| Polygon & S3path retrieval | ✅ Implemented |
| Presence on Ifremer storage | ✅ Implemented |
| Dataset membership from listings | ✅ Implemented |
| `--stats` command | ⏳ Stub (basic statistics implemented) |
| `--backup` command | ⏳ Stub |
| `--update` command | ⏳ Stub |
| `query` method | ⏳ Stub |
| Meteorological enrichment | ⏳ Stub |
| Derived products (A21/B17) | ⏳ Stub |

---

*Document updated – reflects all implementation decisions made during the development of v1.*