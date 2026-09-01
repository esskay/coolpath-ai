"""Main FastAPI application entrypoint for CoolPath AI."""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes import router as api_router
from app.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("coolpath.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifespan management."""
    logger.info(f"*** Starting {settings.APP_NAME} v{settings.APP_VERSION} ***")
    logger.info(f"FortyGuard Mode: {'MOCK/SIMULATION' if settings.USE_MOCK_FORTYGUARD or not settings.FORTYGUARD_API_KEY else 'LIVE API'}")
    logger.info(f"Default H3 Resolution: {settings.DEFAULT_H3_RESOLUTION}")
    yield


# Initialize FastAPI App
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Hyperlocal Thermal Routing Engine using FortyGuard's 2-Meter Street-Level Temperature AI.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Router
app.include_router(api_router)

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Empty favicon response to prevent 404."""
    from fastapi import Response
    return Response(status_code=204)

# Mount frontend directory for static assets
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        """Serve the single-page dashboard."""
        return FileResponse(os.path.join(frontend_dir, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
