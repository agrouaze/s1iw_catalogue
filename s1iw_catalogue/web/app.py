"""FastAPI application for s1iw_catalogue web interface."""

import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from s1iw_catalogue.web.routes import stats, browse
from s1iw_catalogue.web.utils.data_loader import catalogue_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup: Load catalogue
    catalogue_path = os.environ.get("S1IW_CATALOGUE_PATH")
    if catalogue_path:
        catalogue_manager.load(Path(catalogue_path))
        print(f"Loaded catalogue: {catalogue_path}")
    else:
        print("Warning: S1IW_CATALOGUE_PATH not set. Use --catalogue flag.")
    
    yield
    
    # Shutdown: Clean up
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
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(browse.router, prefix="/api/browse", tags=["browse"])

# Static files (optional, for future frontend)
# app.mount("/static", StaticFiles(directory="s1iw_catalogue/web/static"), name="static")


@app.get("/")
async def root():
    """Root endpoint returning API info."""
    return {
        "name": "s1iw_catalogue API",
        "version": "0.1.0",
        "endpoints": {
            "stats": "/api/stats",
            "browse": "/api/browse",
        },
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "catalogue_loaded": catalogue_manager.is_loaded(),
        "catalogue_path": str(catalogue_manager.path) if catalogue_manager.path else None,
        "row_count": catalogue_manager.row_count(),
    }