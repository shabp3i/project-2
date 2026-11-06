"""
Admin Web UI routes.
Serves the responsive single-page administration dashboard.
"""

from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(tags=["Admin UI"])

STATIC_DIR = Path(__file__).parent.parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"


@router.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect root path to /admin dashboard."""
    return RedirectResponse(url="/admin")


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_dashboard():
    """Serve the Admin Panel single page application."""
    if INDEX_HTML.exists():
        content = INDEX_HTML.read_text(encoding="utf-8")
        return HTMLResponse(content=content)
    return HTMLResponse(
        content="<h1>Admin Panel Not Found</h1><p>index.html is missing.</p>",
        status_code=404,
    )
