# `exhaustiveIfrIW` – Exhaustive Sentinel-1 IW SAFE Catalogue

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
| `polygon of the acquisition from CDSE` | string | Ground footprint polygon (WKT format) as provided by Copernicus Data Space Ecosystem (CDSE) |
| `S3path from CDSE` | string | S3 path (or URL) of the product on CDSE |
| `polarization` | string | One of: `SDV`, `SSV`, `SDH`, `SSH` (Ifremer internal convention) |
| `unité` | string | Satellite identifier: `S1A`, `S1B`, `S1C`, `S1D` |

> **Note**: One row corresponds to **a single unique SAFE** identified by one of the three fields `SAFE SLC`, `SAFE GRD` or `SAFE OCN` (the other two remain empty).  
> The file is time‑partitioned (year/month) to optimise queries.

## 3. Update Workflow

The file is rebuilt or updated **daily** according to the following pipeline:

### 3.1 Read reference listings
- List of SLC / GRD to track (whether stored at Ifremer or not)
- Reference colocalisation listings

### 3.2 CDSE matching
- For each SLC, use `cdse_match_product_type` to find associated GRDs.
- Symmetrically, for each GRD, retrieve the parent SLC.
- Align `SAFE SLC` and `SAFE GRD` columns when a match is possible.

### 3.3 Local Ifremer presence
- Query `s1ifr` to determine whether each SLC and GRD is present on Ifremer servers (populates `presence SLC` / `presence GRD`).

### 3.4 Derived product detection
- Use `familyprod` to identify associated products: A21, B17, OCN, and dataset membership.
- Fill `presence L1B XSP A21`, `presence L1C XSP B17`, `presence OCN` with local paths or `NULL`.

### 3.5 (Optional) Meteorological enrichment
- For each SAFE centroid (computed from the polygon), query ECMWF 0.1° and WW3 grids to obtain `Hs WW3`, `Tp WW3`, `U10 ecmwf`, `v10 ecmwf`.
- This step can be resource‑intensive and run separately (e.g., weekly).

### 3.6 Merge / deduplication
- If a SAFE already exists in the file, **merge** the information: new presence paths complement or overwrite old ones.
- No duplicate rows are allowed.

### 3.7 Writing
- Save a new version of the `.parquet` (with time partitioning).
- Keep the last 7 versions.

## 4. Data sources and external dependencies

| Source / Tool | Role | Query frequency |
|---------------|------|------------------|
| `cdse_match_product_type` | SLC ↔ GRD matching | Per new SAFE |
| `s1ifr` | Ifremer storage presence | Daily |
| `familyprod` | Derived products (A21, B17, OCN) and datasets | Daily |
| Reference listings (local) | Define SAFE set to track | Variable (manual or scripted) |
| ECMWF / WW3 (API or files) | Meteorological variables | Optional, typically weekly |

## 5. Technical requirements

- **Language**: Python 3.10+ (recommended: `polars` or `pandas` + `pyarrow`)
- **Parquet**: `snappy` or `zstd` compression
- **Parallelism**: Use Ifremer HPC for heavy processing (no resource constraints)
- **Scheduling**: Cron or Airflow for daily execution
- **Storage**: Sufficient disk space for the final file and its versions (tens of GB eventually)

## 6. Main use cases

1. **Monitoring dashboard**  
   - Aggregate presence ratios (SLC available? GRD available? A21 generated?)  
   - Track dataflow progression

2. **SAFE name lookup page**  
   - Enter product name (SLC, GRD, or OCN)  
   - Display status of each column (`presence`, `dataset`, meteorological data, etc.)

3. **Spatio‑temporal heatmaps**  
   - For a given dataset (e.g., `sarwave`), produce maps of `Hs WW3` or `U10` using centroids derived from polygons.

## 7. Points of vigilance

- **SLC ↔ GRD matching**: Not always one‑to‑one. One SLC may produce several GRDs (temporal splitting). The business rule must be explicit in the code (e.g., pick the most representative GRD).
- **`dataset(s) d'appartenance` column**: Although stored as a list, frequent queries for a specific dataset (e.g., `'sarwave' in dataset_list`) may be slow on a large file. Pre‑filtering by partition or an auxiliary boolean column for major datasets is recommended (without altering the schema, this can be handled by materialised views in the consuming tool).
- **Incremental update**: To avoid rebuilding everything daily, compare incoming listings with existing SAFEs (using `start date SAFE` or an index).
- **Source traceability**: Add to the Parquet file metadata (`key_value_metadata`) the list of reference listings used and the generation date.
- **Optional meteorological data**: If too heavy, split into a dedicated `.parquet` file and join during queries.

## 8. Next steps

1. Define the exact format of reference listings.
2. Implement a prototype on a subset (1 month of data).
3. Validate SLC ↔ GRD matching on CDSE.
4. Deploy the daily workflow on the HPC with logging.

---

*Document approved – columns are fixed according to the specification above. Any future evolution will require a new version of the schema.*