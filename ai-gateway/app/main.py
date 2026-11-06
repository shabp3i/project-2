"""
Main application entry point for AI Gateway.
Initializes FastAPI, mounts CORS, routers, and database lifecycle.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .database import init_db, get_upstream_config
from .routes.openai import router as openai_router
from .routes.admin_api import router as admin_api_router
from .routes.admin_ui import router as admin_ui_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events: initialize SQLite database on startup."""
    logger.info("Initializing SQLite database tables...")
    await init_db()
    cfg = await get_upstream_config()
    logger.info(f"AI Gateway started successfully!")
    logger.info(f"-> Upstream Base URL: {cfg['upstream_base_url']}")
    logger.info(f"-> Admin Panel: http://localhost:{settings.PORT}/admin")
    logger.info(f"-> OpenAI Proxy: http://localhost:{settings.PORT}/v1")
    yield
    logger.info("AI Gateway shutting down.")


app = FastAPI(
    title="Quán Net AI - Gateway & Billing",
    description="OpenAI-compatible proxy gateway with cybercafe credit token billing for Colab llama.cpp",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for OpenCode and browser web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    """
    Format HTTP exceptions properly.
    For /v1/* endpoints, ensures OpenAI-compatible JSON error envelope.
    """
    if request.url.path.startswith("/v1/"):
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": str(exc.detail),
                    "type": "api_error",
                    "code": str(exc.status_code),
                }
            },
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


# Health check
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for Docker and monitoring."""
    cfg = await get_upstream_config()
    return {
        "status": "ok",
        "service": "ai-gateway",
        "upstream_configured": bool(cfg["upstream_base_url"]),
    }


# Register routers
app.include_router(admin_ui_router)
app.include_router(admin_api_router)
app.include_router(openai_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )
