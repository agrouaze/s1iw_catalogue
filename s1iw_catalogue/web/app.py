"""FastAPI application for s1iw_catalogue web interface."""

import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from s1iw_catalogue.web.routes import stats, browse
from s1iw_catalogue.web.utils.data_loader import catalogue_manager
from s1iw_catalogue.web.template_engine import get_templates


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    catalogue_path = os.environ.get("S1IW_CATALOGUE_PATH")
    if catalogue_path:
        catalogue_manager.load(Path(catalogue_path))
        print(f"Loaded catalogue: {catalogue_path}")
    else:
        print("Warning: S1IW_CATALOGUE_PATH not set. Use --catalogue flag.")
    
    yield
    
    catalogue_manager.clear()
    print("Catalogue unloaded")


# Create FastAPI app
app = FastAPI(
    title="s1iw_catalogue API",
    description="API for exploring Sentinel-1 IW catalogues",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up templates
templates = get_templates()

# Mount static files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(BASE_DIR, "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Register API routes
app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(browse.router, prefix="/api/browse", tags=["browse"])


@app.get("/")
async def home(request: Request):
    """Home page with global statistics."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/browse")
async def browse_page(request: Request):
    """Browse page with filters and visualizations."""
    return templates.TemplateResponse("browse.html", {"request": request})


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "catalogue_loaded": catalogue_manager.is_loaded(),
        "catalogue_path": str(catalogue_manager.path) if catalogue_manager.path else None,
        "row_count": catalogue_manager.row_count(),
    }