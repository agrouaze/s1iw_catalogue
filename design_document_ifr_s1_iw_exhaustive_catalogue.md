# s1iw_catalogue – Design Document

## 1. Objective

Build and maintain a single **Parquet** file that centralises, for each SAFE (Sentinel-1 IW product), information on availability, membership in internal datasets, meteorological enrichment, and location. This file must enable fast queries for:

- Monitoring dashboards (data usability percentages for SLC, GRD, OCN, A21, B17, …)
- SAFE name lookup (status and dataset membership of a product)
- Heatmap production (significant wave height, peak period, wind) per dataset
- Catalogue merging for parallel HPC processing

## 2. Parquet File Description

### 2.1 File Name
`sentinel-1_exhaustive_IW_SAFE_working_material.parquet`

### 2.2 Column Schema

| Column name | Type | Description |
|-------------|------|-------------|
| `SAFE SLC` | string | SAFE name when it is an SLC product (empty otherwise) |
| `SAFE GRD` | string | SAFE name when it is a GRD product (empty otherwise) |
| `SAFE OCN` | string | SAFE name when it is an OCN product (or `"NOT_FOUND"` if searched but absent) |
| `PATH SLC` | string | Local path or `NULL` indicating SLC presence on Ifremer storage |
| `PATH GRD` | string | Local path or `NULL` for GRD |
| `PATH OCN` | string | Local path or `NULL` for OCN |
| `PATH L1B XSP A21` | string | Local path or `NULL` for derived product A21 (L1B XSP) |
| `PATH L1C XSP B17` | string | Local path or `NULL` for derived product B17 (L1C XSP) |
| `datasets` | string[] | List of dataset names the SAFE belongs to (e.g., `["ciaran2023", "jolina26"]`). Assigned at build time from listing file names. |
| `category` | string | Dataset category: `undefined`, `train`, `val`, `test`, `case-study` (priority hierarchy: undefined < train < val < test) |
| `Hs WW3` | float | Significant wave height (m) from WaveWatch III, interpolated to SAFE centroid |
| `Tp WW3` | float | Peak period (s) from WW3 |
| `U10 ecmwf` | float | Zonal wind at 10 m (m/s) from ECMWF (0.1° grid) |
| `V10 ecmwf` | float | Meridional wind at 10 m (m/s) from ECMWF |
| `start date SAFE` | timestamp | Acquisition start date (extracted from the SAFE name) |
| `horodating` | timestamp | Date and time when this row was **last updated** in the catalogue (system time) |
| `polygon SLC` | string | Ground footprint polygon (WKT format) for the SLC product from CDSE |
| `polygon GRD` | string | Ground footprint polygon (WKT format) for the GRD product from CDSE |
| `S3path SLC` | string | S3 path (or URL) of the SLC product on CDSE |
| `S3path GRD` | string | S3 path (or URL) of the GRD product on CDSE |
| `polarization` | string | One of: `SDV`, `SSV`, `SDH`, `SSH` (Ifremer internal convention) |
| `unit` | string | Satellite identifier: `S1A`, `S1B`, `S1C`, `S1D` |

> **Note**:
> - One row corresponds to **a single unique SAFE** identified by one of the three fields `SAFE SLC`, `SAFE GRD` or `SAFE OCN` (the two others remain empty).
> - The `horodating` column tracks when the row was last modified, enabling incremental updates and monitoring of catalogue freshness.
> - Polygon and S3path columns are split into SLC and GRD variants because footprints and storage paths differ between product types.
> - `datasets` is populated at build time directly from the configuration structure (dataset names from listing file keys).
> - `category` is computed from the `datasets` list using priority hierarchy. Conflicts are logged to a separate file.

## 3. Core Logic: The Build and Link Workflow

The core of the library is the `core_update()` method in `CatalogueUpdater`. It orchestrates a multi-step pipeline to transform raw listings into a fully linked and enriched catalogue.

### 3.1 Overview of the `core_update()` Pipeline

The method executes the following steps in order:

1. **Build from listings** (`build_from_listings`)
   - Reads SLC and GRD listings from the configuration.
   - Each listing file is associated with a dataset name and category.
   - Creates initial DataFrame with one row per SAFE product.
   - Populates `datasets` with the dataset name(s) from the listing(s).
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
   - Category is computed using priority hierarchy.
   - Meteorological columns take first non-null value.
   - `horodating` takes the most recent timestamp.
   - Splits polygon and S3path columns into SLC/GRD variants.

5. **Fetch polygons and S3 paths** (`_update_polygons_and_s3paths`)
   - Queries CDSE using `cdsodatacli.query.fetch_data`.
   - Only fetches for products missing polygon or S3path information.
   - Uses exact start/end dates extracted from SAFE names.
   - Supports local caching via `cdse_cache_dir` configuration.

6. **Check presence on Ifremer storage** (`_update_presence_columns`)
   - Uses `s1ifr.get_path_from_base_safe` to check if products exist.
   - Checks all configured archives (datawork, scale, etc.) sequentially.
   - Stores the full path if found, otherwise `NULL`.

7. **Check derived products** (`_update_derived_products`)
   - Uses `s1ifr.paths_safe_product_family.get_products_family` to find L1B, L1C, L2WAV products.
   - Batch processing for efficiency.

### 3.2 Visual Pipeline Flow

```
Raw Listings (SLC + GRD)
        │
        ▼
┌─────────────────────────────┐
│ build_from_listings()       │  ← Dataset names & categories assigned
│  - Read SLC listings        │
│  - Read GRD listings        │
│  - Assign datasets & category│
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│ _local_link_slc_grd()       │  ← Local matching (fast, no API)
│  - Match by data_take       │
│  - Time window ±5s          │
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│ _cdse_fallback_link()       │  ← CDSE API for orphans (multi-threaded)
│  - GRD orphans → SLC        │
│  - SLC orphans → GRD        │
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│ _merge_linked_rows()        │  ← Merge pairs into one row
│  - Union datasets           │
│  - Compute category         │
│  - Split poly/S3path        │
│  - Most recent horodate     │
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│ _link_ocn_to_grd/slc()      │  ← Link OCN products
│  - Primary: GRD → OCN       │
│  - Fallback: SLC → OCN      │
│  - Store "NOT_FOUND" in SAFE OCN│
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│ _update_polygons...()       │  ← CDSE for footprints (with cache)
│  - Get WKT polygons         │
│  - Get S3 paths             │
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│ _update_presence...()       │  ← Ifremer storage check
│  - Check datawork/scale     │
│  - Store full paths         │
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│ _update_derived_products()  │  ← Derived products (L1B, L1C, L2WAV)
│  - Batch processing         │
└─────────────────────────────┘
        │
        ▼
   Final Catalogue
```

## 4. Command-Line Interface (CLI)

The tool provides a command-line interface with several subcommands:

### 4.1 `catalog-iw --create`

Create a brand new `.parquet` catalogue from scratch.

```
catalog-iw --config /path/to/config.yml create --output /path/to/catalogue.parquet
```

Create a catalogue for a single listing (useful for parallel HPC processing):

```
catalog-iw --config /path/to/config.yml create --output /path/to/cat_dataset.parquet --listing ciaran2023
```

Behaviour:
- Reads reference listings (SLC/GRD) from configuration.
- Dataset names and categories are taken from the listing file keys in the config.
- Executes the full pipeline (all 7 steps described above).
- Sets `horodating` to current timestamp for all rows.
- Overwrites any existing file at the output path.

### 4.2 `catalog-iw --update`

Update the existing catalogue incrementally.

```
catalog-iw --update --catalogue /path/to/catalogue.parquet --config /path/to/config.yml
```

Behaviour:
- Reads existing catalogue.
- Identifies SAFE rows that need updates based on:
  - New products appearing in reference listings.
  - Changes in `PATH` columns (new paths discovered).
  - Missing enrichment columns.
- **Columns that already have a value are NOT overwritten** unless explicitly forced.
- Only updates the `horodating` column for rows that actually changed.
- Appends new rows for previously unknown SAFE.

Update rules per column family:

| Column family | Update behaviour |
|---------------|------------------|
| `PATH *` | Fill if empty; never overwrite an existing path |
| `datasets` | Merge new datasets; preserve existing ones |
| `category` | Recompute based on merged datasets using priority hierarchy |
| `Hs WW3`, `Tp WW3`, `U10 ecmwf`, `V10 ecmwf` | Fill if empty; optional `--force-meteo` to refresh |
| `horodating` | Always set to current time when row is modified |
| `start date SAFE`, `polygon SLC/GRD`, `S3path SLC/GRD`, `polarization`, `unit` | Set once at creation; never updated |

### 4.3 `catalog-iw --stats`

Print statistics about the catalogue.

```
catalog-iw --stats --catalogue /path/to/catalogue.parquet [--dataset ciaran2023] [--verbose]
```

Output includes:
- Total number of SAFE entries.
- Count and percentage of SLC, GRD, OCN products.
- For each dataset:
  - Number of SAFE belonging to that dataset.
  - Percentage of complete presence (SLC/GRD/OCN available).
- Latest ingested SAFE in **acquisition time** (`start date SAFE`).
- Latest ingested SAFE in **horodating time** (when last updated in catalogue).
- Global statistics per `unit` (S1A, S1B, etc.) and per `polarization`.
- Optional: export statistics as JSON (`--output stats.json`).

### 4.4 `catalog-iw --backup`

Save a timestamped copy of the current catalogue.

```
catalog-iw --backup --catalogue /path/to/catalogue.parquet [--backup-dir /path/to/backups]
```

Behaviour:
- Creates a copy named `catalogue_YYYYMMDD_HHMMSS.parquet` in the backup directory.
- Preserves the original file unchanged.
- Keeps only the last N backups (configurable, default 7).
- Useful before running `--update` or `--create` on a production catalogue.

### 4.5 `catalog-iw --merge`

Merge multiple catalogues into a single file.

```
catalog-iw --config /path/to/config.yml merge catalogue1.parquet catalogue2.parquet --output merged.parquet
```

Behaviour:
- Reads all input catalogues.
- Identifies rows by `SAFE SLC`, `SAFE GRD`, or `SAFE OCN`.
- For duplicates:
  - `datasets`: UNION of all lists.
  - `category`: highest priority (test > val > train > undefined).
  - `horodating`: keep the most recent.
  - `PATH *`: keep first non-null (prefer the most recent `horodating`).
  - `polygon` and `S3path`: keep first non-null.
- Writes the merged catalogue with config metadata.

### 4.6 `catalog-iw --serve`

Launch the web interface for visual exploration.

```
catalog-iw --config /path/to/config.yml serve --catalogue /path/to/catalogue.parquet
```

Options:
- `--host` (default: `127.0.0.1`)
- `--port` (default: `8649`)
- `--reload` (development mode)

The web interface provides:
- Dashboard with global stats and dataset completeness table
- Browse page with filters, map, charts, and results table

### 4.7 `catalog-iw --config` (global option)

All commands accept a `--config` option to specify which configuration file to use.

```
catalog-iw --config /etc/s1iw/production.yml create --output catalogue.parquet
```

If not provided, the tool looks for `config.yml` in the current working directory, then in `~/.config/s1iw_catalogue/config.yml`, then falls back to default settings.

## 5. Configuration System

### 5.1 Configuration Hierarchy

The tool uses a layered configuration system (higher priority overrides lower):

1. **Command-line arguments** (highest priority)
2. **Local configuration** (`localconfig.yml` – NOT versioned)
3. **Versioned configuration** (`config.yml` – committed to Git)
4. **Default built-in values** (lowest priority)

### 5.2 `config.yml` (versioned, shared across team)

```
# config.yml – Versioned configuration (commit to Git)

paths:
  reference_listings:
    ciaran2023:
      path: "/shared/listings/slc_ciaran2023.txt"
      type: "slc"
      description: "Storm Ciaran over Europe"
      category: "case-study"
    jolina26:
      path: "/shared/listings/grd_jolina26.txt"
      type: "grd"
      description: "Medicane Jolina over Mediterranean"
      category: "case-study"
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

product_versions:
  l1b: ["A21", "A23"]
  l1c: ["B17", "B21"]

cdse_cache_dir: "/shared/cache/cdse"
```

### 5.3 `localconfig.yml` (NOT versioned, user/infrastructure specific)

```
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

cdse_cache_dir: "/scratch/agrouaze/cdse_cache"
```

### 5.4 Configuration Loading Logic

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

### 5.5 `.gitignore` updates

```
# Exclude local configuration
localconfig.yml

# Exclude generated version file (if using hatch-vcs)
s1iw_catalogue/_version.py

# Exclude catalogue files (if stored locally)
*.parquet
backups/
checkpoints/
```

## 6. Dataset Categories and Priority

The `category` column tracks the dataset category for each row. If a SAFE belongs to multiple datasets with different categories, the highest priority wins:

| Category | Priority |
|----------|----------|
| `undefined` | 0 (lowest) |
| `train` | 1 |
| `val` | 2 |
| `test` | 3 |
| `case-study` | 4 (highest) |

When conflicts occur, a report is written to `conflicts_YYYYMMDD_HHMMSS.txt` in the same directory as the catalogue, listing each conflict and the chosen category.

## 7. The `horodating` Column

The `horodating` column (timestamp) tracks **catalogue modification time** per row.

### 7.1 Purpose

- Know **when** a specific SAFE was last updated in the catalogue.
- Distinguish between acquisition date (`start date SAFE`) and catalogue ingestion date (`horodating`).
- Enable incremental `--update` logic: only process rows older than a certain threshold.
- Debugging: identify stale rows that may need manual refresh.

### 7.2 Update Rules

- **On `--create`**: set to current timestamp for all rows.
- **On `--update`**:
  - For rows that have **any column changed**: set `horodating = now()`.
  - For rows with no changes: leave `horodating` untouched.
- **Never** reset `horodating` to an older value.

### 7.3 Usage in `--stats`

```
catalog-iw --stats --catalogue catalogue.parquet
```

Example output:
```
Catalogue Statistics (as of 2026-07-01 14:30:22)
================================================
Total SAFE entries: 92
  - SLC: 92 (100.0%)
  - GRD: 92 (100.0%)
  - OCN: 72 (78.3%)

Dataset membership:
  - ciaran2023: 71 products
  - jolina26: 21 products

Category distribution:
  - case-study: 92 products

Latest acquisition (start date): 2026-06-30 05:18:31 (SAFE S1D_IW_SLC_...)
Latest catalogue update (horodating): 2026-07-01 14:28:15 (SAFE S1A_IW_SLC_...)

Rows never updated since creation: 0 (0.0%)
Rows older than 30 days (horodating): 0 (0.0%)
```

## 8. Update Workflow

The daily update workflow respects the configuration and incremental update rules:

### 8.1 Daily cron / scheduled task

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

### 8.2 Incremental update logic (detailed)

The `--update` command performs these steps:

1. **Load existing catalogue** into memory (using Polars for efficient Parquet I/O).
2. **Read reference listings** from `config.yml` to identify new products.
3. **Identify new SAFE** not present in catalogue → append rows.
4. **Identify existing SAFE** that may need updates based on:
   - New presence paths found on Ifremer storage.
   - Missing polygon/S3path information.
   - Missing meteorological data (if `force_meteo_refresh` is true).
5. **For each candidate row**:
   - Query `s1ifr` for latest presence (if PATH columns are empty).
   - Query CDSE for polygon and S3path (if missing).
   - Optionally refresh ECMWF/WW3 data.
   - If any column changed → update row and set `horodating = now()`.
6. **Write updated catalogue** (atomic: write to temp file, then rename).
7. **Log changes**: number of new rows, number of updated rows, number of unchanged rows.

## 9. Data Sources and External Dependencies

| Source / Tool | Role | Query frequency | Configurable |
|---------------|------|-----------------|--------------|
| `cdsodatacli.scripts.match_s1_product_types` | SLC ↔ GRD matching for orphans (multi-threaded) | Per new SAFE | Endpoint, timeout, checkpointing |
| `cdsodatacli.query.fetch_data` | Polygon and S3path retrieval | Once per product (if missing) | Endpoint, timeout, cache dir |
| `s1ifr.get_path_from_base_safe` | Ifremer storage presence | Once per product (if missing) | Config file, archives |
| `s1ifr.paths_safe_product_family.get_products_family` | Derived products (L1B, L1C, L2WAV) | Batch processing | Config file, versions |
| Reference listings (local) | Define SAFE set to track | Per update | File paths in config |
| ECMWF / WW3 (API or files) | Meteorological variables | Optional, weekly | Enabled/disabled, grid |

## 10. Technical Requirements

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

## 11. Main Use Cases

1. **Monitoring dashboard**
   - Aggregate presence ratios (SLC available? GRD available? A21 generated?)
   - Track dataflow progression over acquisition time and horodating time

2. **SAFE name lookup page**
   - Enter product name (SLC, GRD, or OCN)
   - Display status of each column (`PATH`, `datasets`, `category`, meteorological data, horodating)

3. **Spatio‑temporal heatmaps**
   - For a given dataset (e.g., `ciaran2023`), produce maps of `Hs WW3` or `U10` using centroids derived from polygons.

4. **Data quality monitoring**
   - Use `--stats` to detect stale rows (old `horodating`) or missing enrichments.

## 12. Points of Vigilance

- **SLC ↔ GRD matching**: Local matching uses `data_take_id` + mission + polarization + time window (±5s). CDSE fallback (multi-threaded with checkpointing) handles cases where local matching fails.
- **`horodating` column**: Essential for incremental updates but adds storage overhead (a few bytes per row). Acceptable.
- **Configuration security**: `localconfig.yml` may contain credentials. Add to `.gitignore`.
- **Atomic updates**: Always write to a temporary file before renaming to avoid corrupting the catalogue if the update fails mid‑way.
- **Backup retention**: Keep old backups to allow manual recovery. Default 7 days.
- **Performance of `--stats`**: On a large catalogue, computing percentages in real time may be slow. Consider caching statistics or using Parquet metadata.
- **ECMWF/WW3 optional**: If too heavy, disable in `config.yml` and run separately.
- **Polygon/S3path columns**: Split into SLC and GRD variants to preserve product-specific information.
- **Dataset membership**: Assigned at build time from listing file names, not updated later.
- **OCN "NOT_FOUND"**: Stored in `SAFE OCN` to avoid re-querying missing products.
- **CDSE caching**: Enabled via `cdse_cache_dir` to reduce API calls and speed up subsequent runs.
- **Checkpointing**: Used in multi-threaded CDSE matching to resume interrupted runs.

## 13. Future Enhancements (Not in Scope for v1)

- `catalog-iw --diff` – compare two catalogues and show changes.
- `catalog-iw --export` – export to CSV, GeoJSON, or Zarr.
- `catalog-iw --watch` – daemon mode that watches for new products and updates in real time.
- Web API (FastAPI) wrapper around the catalogue for remote queries.
- Integration with `dask` for parallel processing on HPC.
- Meteorological enrichment (ECMWF/WW3) with improved interpolation.

## 14. Implementation Status

| Feature | Status |
|---------|--------|
| Configuration loader | ✅ Implemented |
| `--create` command | ✅ Implemented |
| `--create --listing` option | ✅ Implemented |
| Local SLC-GRD matching | ✅ Implemented |
| CDSE fallback matching (multi-threaded) | ✅ Implemented |
| Merging linked rows | ✅ Implemented |
| OCN linking (GRD→OCN, SLC→OCN) | ✅ Implemented |
| "NOT_FOUND" in SAFE OCN | ✅ Implemented |
| Polygon & S3path retrieval | ✅ Implemented |
| CDSE caching | ✅ Implemented |
| Presence on Ifremer storage | ✅ Implemented |
| Dataset membership from listings | ✅ Implemented |
| Dataset category with priority | ✅ Implemented |
| Conflict reporting | ✅ Implemented |
| Derived products (L1B, L1C, L2WAV) | ✅ Implemented |
| `--stats` command | ✅ Implemented |
| `--merge` command | ✅ Implemented |
| `--backup` command | ⏳ Stub |
| `--update` command | ✅ Implemented |
| `query` method | ⏳ Stub |
| Meteorological enrichment | ⏳ Stub |
| Web interface (`--serve`) | ✅ Implemented |

---

*Document updated – reflects all implementation decisions and column naming conventions as of July 2026.*
