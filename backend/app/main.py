from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from datetime import datetime
import logging

from app.api.v1.router import api_router
from app.config import settings
from app.core.database import init_db
from app.core.logging import setup_logging
from app.utils.exceptions import BiodataException

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.VERSION}")
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="Backend API for biodata-assistant - solving cancer researchers' data acquisition pain points",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/api/v1")

# Global exception handlers
@app.exception_handler(BiodataException)
async def biodata_exception_handler(request: Request, exc: BiodataException):
    """Handle custom biodata exceptions."""
    return JSONResponse(
        status_code=500,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
            "timestamp": datetime.utcnow().isoformat()
        }
    )

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """Handle 404 errors."""
    return JSONResponse(
        status_code=404,
        content={
            "detail": "Resource not found",
            "timestamp": datetime.utcnow().isoformat()
        }
    )

@app.exception_handler(500)
async def internal_server_error_handler(request: Request, exc: Exception):
    """Handle internal server errors."""
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "timestamp": datetime.utcnow().isoformat()
        }
    )

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with basic API information."""
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "online",
        "timestamp": datetime.utcnow().isoformat(),
        "docs": "/docs",
        "health": "/api/v1/health"
    }

# Health check endpoint at root level
@app.get("/health")
async def health():
    """Simple health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
