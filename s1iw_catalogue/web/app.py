"""FastAPI application for s1iw_catalogue web interface."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from s1iw_catalogue.web.routes import browse, stats
from s1iw_catalogue.web.template_engine import get_templates
from s1iw_catalogue.web.utils.data_loader import catalogue_manager

logging.getLogger("s1iw_catalogue.catalogue").setLevel(logging.DEBUG)


def create_app(catalogue_path: Path | None = None, config_path: Path | None = None) -> FastAPI:
    """Factory to create the FastAPI app (avoids heavy module-level imports)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Startup/shutdown: loads catalogue and dataset metadata."""
        if catalogue_path:
            catalogue_manager.load(catalogue_path)
            print(f"Loaded catalogue: {catalogue_path}")

            if config_path:
                try:
                    with open(config_path, 'r') as f:
                        config_data = yaml.safe_load(f)
                    
                    # ✅ Replicated logic from catalogue.py (no heavy imports!)
                    reference_listings = config_data.get("paths", {}).get("reference_listings", {})
                    
                    dataset_metadata = {}
                    for dataset_name, dataset_info in reference_listings.items():
                        if not isinstance(dataset_info, dict):
                            continue
                        
                        if "path" in dataset_info:
                            dataset_metadata[dataset_name] = {
                                "description": dataset_info.get("description", ""),
                                "category": dataset_info.get("category", "undefined"),
                                "type": dataset_info.get("type", ""),
                            }
                    
                    catalogue_manager.set_dataset_metadata(dataset_metadata)
                    
                    print(f"Loaded dataset metadata from: {config_path}")
                    print(f"  Datasets found: {list(dataset_metadata.keys())}")
                except Exception as e:
                    print(f"Warning: Could not load dataset metadata: {e}")
            else:
                print("Warning: Config path not set. Dataset metadata unavailable.")
        else:
            print("Warning: Catalogue path not set.")

        yield

        catalogue_manager.clear()
        print("Catalogue unloaded")

    app = FastAPI(
        title="s1iw_catalogue API",
        description="API for exploring Sentinel-1 IW catalogues",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    templates = get_templates()

    # Use Path(__file__) for reliable static file mounting
    BASE_DIR = Path(__file__).parent
    static_dir = BASE_DIR / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

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
            "catalogue_path": (
                str(catalogue_manager.path) if catalogue_manager.path else None
            ),
            "row_count": catalogue_manager.row_count(),
            "dataset_metadata_loaded": catalogue_manager.has_dataset_metadata(),
            "dataset_count": len(catalogue_manager.get_dataset_metadata() or {}),
        }

    return app