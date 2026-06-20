"""Web interface for s1iw_catalogue.

This module provides a FastAPI-based web interface to explore
Sentinel-1 IW catalogues with interactive visualizations.
"""

from s1iw_catalogue.web.app import app
from s1iw_catalogue.web.template_engine import get_templates, CustomTemplates

__all__ = ["app", "get_templates", "CustomTemplates"]