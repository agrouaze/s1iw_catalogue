"""Custom template engine to bypass Jinja2 cache issues."""

from pathlib import Path
from typing import Optional, Dict, Any

from jinja2 import Environment, FileSystemLoader, select_autoescape, Template
from starlette.background import BackgroundTask
from starlette.responses import HTMLResponse


class CustomTemplates:
    """
    Custom template wrapper that bypasses Jinja2's cache issues.
    """
    
    def __init__(self, directory: str):
        self.directory = Path(directory)
        self.env = Environment(
            loader=FileSystemLoader(str(self.directory)),
            autoescape=select_autoescape(["html", "xml"]),
            cache_size=0,
            auto_reload=True,
        )
    
    def TemplateResponse(
        self,
        name: str,
        context: Dict[str, Any],
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
        media_type: Optional[str] = None,
        background: Optional[BackgroundTask] = None,
    ):
        """
        Render a template and return an HTMLResponse.
        """
        # Use the environment's get_template method, but handle cache differently
        # Create a new environment for each template to bypass cache
        env = Environment(
            loader=FileSystemLoader(str(self.directory)),
            autoescape=select_autoescape(["html", "xml"]),
            cache_size=0,
            auto_reload=True,
        )
        
        try:
            template = env.get_template(name)
            content = template.render(**context)
        except Exception as e:
            # Fallback: read file directly
            template_path = self.directory / name
            if not template_path.exists():
                raise FileNotFoundError(f"Template not found: {template_path}")
            
            with open(template_path, "r") as f:
                template_content = f.read()
            
            # Create a Template directly with the environment
            template = Template(template_content)
            template.environment = env
            content = template.render(**context)
        
        return HTMLResponse(
            content=content,
            status_code=status_code,
            headers=headers,
            media_type=media_type or "text/html",
            background=background,
        )


# Singleton instance
_templates: Optional[CustomTemplates] = None


def get_templates(directory: Optional[str] = None) -> CustomTemplates:
    """Get or create the templates instance."""
    global _templates
    if _templates is None:
        if directory is None:
            # Default to the templates directory in the web package
            base_dir = Path(__file__).parent
            directory = str(base_dir / "templates")
        _templates = CustomTemplates(directory)
    return _templates