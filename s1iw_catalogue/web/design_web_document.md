# s1iw_catalogue – Web Interface Design Document

## 1. Overview

The web interface provides a visual exploration layer for the `s1iw_catalogue` Parquet files. It enables users to quickly assess catalogue health, browse products, and visualize spatial/temporal patterns without writing code.

### 1.1 Goals

- Provide an intuitive dashboard for catalogue monitoring
- Enable interactive exploration of products and their metadata
- Visualize spatial distributions (footprints) and relationships
- Support dataset-level completeness assessment
- No authentication required (read-only access)

### 1.2 Non-Goals

- Product download or staging
- Catalogue modification (read-only)
- User authentication/authorization
- High-volume production serving (designed for internal use)

## 2. Architecture

### 2.1 Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Backend | FastAPI | Modern, async, automatic OpenAPI docs |
| Frontend | Jinja2 + Plotly | Server-side rendering with interactive charts |
| Data | Polars + Shapely | Native catalogue format + geometry handling |
| Server | Uvicorn | ASGI server for FastAPI |
| Deployment | Docker | Containerized for reproducibility |

### 2.2 Directory Structure

```
s1iw_catalogue/
├── web/
│   ├── __init__.py
│   ├── app.py                  # FastAPI application
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── stats.py            # Statistics endpoints
│   │   ├── catalogue.py        # Browsing endpoints
│   │   └── geospatial.py       # Map/geometry endpoints
│   ├── templates/
│   │   ├── base.html           # Base template with layout
│   │   ├── index.html          # Home page (statistics)
│   │   └── browse.html         # Browse page (exploration)
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css       # Custom styles
│   │   └── js/
│   │       ├── dataset_table.js # Table interactivity
│   │       └── filters.js      # Filter logic
│   └── utils/
│       ├── __init__.py
│       ├── data_loader.py      # Catalogue loading/caching
│       └── visualizations.py   # Plotly chart generators
```

### 2.3 Data Flow

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Catalogue      │───▶│  FastAPI        │───▶│  Jinja2         │
│  .parquet       │    │  Backend        │    │  Templates      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │                        │
                              ▼                        ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │  Plotly         │    │  Static         │
                       │  Visualizations │    │  Assets         │
                       └─────────────────┘    └─────────────────┘
```

## 3. Pages

### 3.1 Home Page (`/`)

**Purpose**: Provide a high-level overview of catalogue health and dataset completeness.

**Sections**:

#### 3.1.1 Global Statistics Cards
- Total SAFE entries
- SLC count (with percentage)
- GRD count (with percentage)  
- OCN count (with percentage)
- Linked pairs count

#### 3.1.2 Dataset Completeness Table

A matrix table showing each dataset's completeness across all presence columns.

**Table Structure**:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Dataset │ SLC    │ GRD    │ OCN    │ L1B A21 │ L1C B17 │ L2 E11 │ L2 E13 │ Overall  │
│ ────────┼────────┼────────┼────────┼─────────┼─────────┼────────┼────────┼───────────│
│ hibou2  │ 🟢 95% │ 🟢 95% │ ⚪ 0%  │ 🟡 80%  │ 🟡 80%  │ 🟡 75% │ 🟡 75% │ 🟡 76%   │
│ zebra   │ 🟢 92% │ 🟢 92% │ ⚪ 0%  │ 🟢 88%  │ 🟢 88%  │ 🟡 82% │ 🟡 82% │ 🟡 80%   │
│ castor5 │ 🟡 65% │ 🟡 65% │ ⚪ 0%  │ 🟡 60%  │ 🟡 60%  │ 🔴 45% │ 🔴 45% │ 🔴 51%   │
│ lion    │ 🟢 90% │ 🟢 90% │ ⚪ 0%  │ 🟡 70%  │ 🟡 70%  │ 🟡 55% │ 🟡 55% │ 🟡 63%   │
│ ────────┼────────┼────────┼────────┼─────────┼─────────┼────────┼────────┼───────────│
│ Overall │ 🟢 88% │ 🟢 87% │ ⚪ 0%  │ 🟡 76%  │ 🟡 76%  │ 🟡 68% │ 🟡 68% │ 🟡 70%   │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Color Coding**:

| Percentage | Color | Emoji |
|------------|-------|-------|
| ≥ 80% | Green | 🟢 |
| 50% - 79% | Yellow | 🟡 |
| 1% - 49% | Red | 🔴 |
| 0% | Grey | ⚪ |

**Interactive Features**:
- Click column headers to sort
- Hover shows exact percentage
- Click dataset row to filter browse page

#### 3.1.3 Presence Completeness Summary (Optional)
A compact view showing overall presence percentages per column as a bar chart or donut chart.

### 3.2 Browse Page (`/browse`)

**Purpose**: Explore the catalogue with filters and visualizations.

#### 3.2.1 Filters Panel

| Filter | Type | Description |
|--------|------|-------------|
| `SAFE SLC` | Text | Partial match on SLC name |
| `SAFE GRD` | Text | Partial match on GRD name |
| `SAFE OCN` | Text | Partial match on OCN name |
| `Dataset` | Dropdown | Select one or more datasets |
| `Polarization` | Dropdown | SDV, SSV, SDH, SSH |
| `Satellite (unité)` | Dropdown | S1A, S1B, S1C, S1D |
| `Date Range` | Date picker | start date SAFE |
| `Presence Status` | Checkbox | Show only products with SLC/GRD/OCN presence |

**Behaviour**:
- All filters are optional
- Filters are AND-combined
- Results update in real-time (debounced)

#### 3.2.2 Visualizations Grid (2x2 layout)

**Map (Top Left)**
- Displays footprints of filtered products (max 100)
- Uses Shapely to extract WKT polygons
- Colored by dataset or polarization
- Interactive hover shows product name
- Zoom to selection

**Daily Acquisitions Bar Chart (Top Right)**
- Aggregates products by acquisition date
- Color-coded by product type (SLC/GRD/OCN)
- Hover shows exact count per day

**Multi-level Pie Chart (Bottom Left)**
- Outer ring: Polarization (SDV, SSV, etc.)
- Inner ring: Satellite (unité) per polarization
- Click to drill down

**Hs vs Tp Heatmap (Bottom Right)**
- Scatter/hexbin plot of Hs (WW3) vs Tp (WW3)
- Color scale by density
- Only for products with both values available

**Optional: Wind Direction vs Wind Speed Heatmap**
- To be added as a toggle or additional row

#### 3.2.3 Results Table (Below Visualizations)
- Paginated list of filtered products
- Columns: SAFE SLC, SAFE GRD, Dataset, start date, horodating, polarization, unité
- Click row to expand full details
- Export filtered results to CSV

## 4. API Endpoints

### 4.1 Statistics Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/stats/global` | GET | Global statistics |
| `/api/stats/datasets` | GET | Dataset completeness matrix |
| `/api/stats/presence` | GET | Overall presence percentages |

### 4.2 Browse Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/browse/filter` | POST | Filter catalogue with JSON payload |
| `/api/browse/map` | POST | Get filtered products for map (geometry + metadata) |
| `/api/browse/heatmap/hs_tp` | POST | Get Hs/Tp data for heatmap |
| `/api/browse/heatmap/wind` | POST | Get wind direction/speed data |

### 4.3 Payload Examples

**Filter Request**:

```
{
    "slc_name": "S1A",
    "grd_name": null,
    "ocn_name": null,
    "datasets": ["hibou2", "zebra"],
    "polarization": ["1SDV"],
    "satellites": ["S1A", "S1B"],
    "date_start": "2024-01-01",
    "date_end": "2024-12-31",
    "has_slc": null,
    "has_grd": true,
    "has_ocn": false,
    "limit": 100,
    "offset": 0
}
```

## 5. Performance Considerations

### 5.1 Caching Strategy

| Data | Cache Duration | Invalidation |
|------|----------------|--------------|
| Global stats | 1 hour | On catalogue update |
| Dataset completeness | 1 hour | On catalogue update |
| Map polygons | 5 minutes | On filter change |
| Heatmap data | 5 minutes | On filter change |

### 5.2 Optimization Techniques

- **Lazy loading**: Load visualizations only when visible
- **Polygon simplification**: Use Shapely simplify with tolerance
- **Limit polygons**: Max 100 footprints on map
- **Downsampling**: For heatmaps with >10k points
- **Pagination**: Table results limited to 100 rows per page

## 6. User Interface Guidelines

### 6.1 Responsive Design

| Breakpoint | Layout |
|------------|--------|
| ≥ 1200px | Full 2x2 grid |
| 768-1199px | Stacked layout (map + charts) |
| < 768px | Single column, compact tables |

### 6.2 Color Palette

| Element | Color | Hex |
|---------|-------|-----|
| Primary | Dark Blue | `#2c3e50` |
| Secondary | Light Grey | `#f8f9fa` |
| Success (Green) | `≥80%` | `#28a745` / `#d4edda` |
| Warning (Yellow) | `50-79%` | `#ffc107` / `#fff3cd` |
| Danger (Red) | `1-49%` | `#dc3545` / `#f8d7da` |
| Secondary (Grey) | `0%` | `#6c757d` / `#e9ecef` |

### 6.3 Typography

- Font: System fonts (sans-serif)
- Headings: 1.5rem, bold
- Body: 0.9rem, regular
- Table: 0.8rem, regular

## 7. Development Phases

### Phase 1: Backend API (Week 1)
- FastAPI app with route structure
- Statistics endpoints
- Filter endpoints
- Heatmap data preparation

### Phase 2: Frontend Pages (Week 2)
- Base template + CSS
- Home page with stats + dataset table
- Browse page with filters + visualizations
- Plotly chart integration

### Phase 3: Polish & Deployment (Week 3)
- Responsive design
- Performance optimization
- Dockerfile
- Documentation

## 8. Dependencies

### 8.1 Core Dependencies

```
[project.optional-dependencies]
web = [
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "plotly>=5.18.0",
    "jinja2>=3.1.0",
    "python-multipart>=0.0.6",
    "shapely>=2.0.0",
    "geopandas>=0.14.0",
    "pandas>=2.0.0",
]
```

### 8.2 Optional Dependencies

```
web = [
    # ... plus:
    "orjson>=3.9.0",           # Faster JSON serialization
    "httpx>=0.25.0",           # For async HTTP client
]
```

## 9. CLI Integration

```
@main.command()
@click.option("--host", default="127.0.0.1", help="Host to bind the web server to.")
@click.option("--port", default=8080, type=int, help="Port to bind the web server to.")
@click.option("--catalogue", "-c", required=True, type=click.Path(exists=True), help="Catalogue .parquet file to serve.")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development.")
@click.pass_context
def serve(ctx: click.Context, host: str, port: int, catalogue: Path, reload: bool) -> None:
    """Launch web interface to explore the catalogue."""
    os.environ["S1IW_CATALOGUE_PATH"] = str(catalogue)
    import uvicorn
    from s1iw_catalogue.web.app import app
    uvicorn.run("s1iw_catalogue.web.app:app", host=host, port=port, reload=reload)
```

## 10. Deployment

### 10.1 Dockerfile

```
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml Makefile ./
RUN pip install -e ".[web]"

COPY s1iw_catalogue/ ./s1iw_catalogue/

ENV S1IW_CATALOGUE_PATH=/data/catalogue.parquet

EXPOSE 8080

CMD ["catalog-iw", "serve", "--catalogue", "/data/catalogue.parquet", "--host", "0.0.0.0", "--port", "8080"]
```

### 10.2 Run Commands

```
# Development
catalog-iw serve --catalogue catalogue.parquet --reload

# Production with Gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker s1iw_catalogue.web.app:app

# Docker
docker build -t s1iw-catalogue-web .
docker run -p 8080:8080 -v /path/to/catalogue:/data s1iw-catalogue-web
```

## 11. Future Enhancements

- **Authentication**: Add optional login for sensitive deployments
- **Export**: Export filtered data as CSV/GeoJSON
- **API Key**: Optional API key for programmatic access
- **WebSocket**: Real-time updates when catalogue changes
- **More visualizations**: Time series, orbit tracks, coverage maps
- **Integration**: Link to external tools (e.g., STAC, OpenDAP)

---

*Document version: 1.0 | Last updated: 2026-06-18*