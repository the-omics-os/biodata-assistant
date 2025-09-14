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
from app.core.services.email_monitoring_service import email_monitoring_service

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management with background services."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.VERSION}")

    # Initialize database
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    # Initialize background services
    try:
        await _initialize_background_services()
        logger.info("Background services initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize background services: {e}")
        # Don't raise here - allow the app to start even if background services fail

    # Log startup completion
    logger.info(f"{settings.APP_NAME} startup completed successfully")

    yield

    # Shutdown
    logger.info("Shutting down application")
    try:
        await _shutdown_background_services()
        logger.info("Background services shut down successfully")
    except Exception as e:
        logger.error(f"Error during background services shutdown: {e}")


async def _initialize_background_services():
    """Initialize and configure background services."""
    services_status = {}

    # Initialize Celery configuration (imported here to avoid circular imports)
    try:
        from app.core.celery_app import celery_app

        # Test Celery connection if enabled
        if settings.ENABLE_BACKGROUND_TASKS:
            # Check if Celery workers are available (non-blocking)
            try:
                inspect = celery_app.control.inspect()
                active_workers = inspect.active()
                if active_workers:
                    services_status["celery"] = "connected"
                    logger.info(f"Celery workers detected: {list(active_workers.keys())}")
                else:
                    services_status["celery"] = "no_workers"
                    logger.warning("No active Celery workers detected. Background tasks may not process.")
            except Exception as e:
                services_status["celery"] = f"error: {str(e)}"
                logger.warning(f"Could not connect to Celery broker: {e}")
        else:
            services_status["celery"] = "disabled"
            logger.info("Background tasks are disabled in configuration")

    except ImportError as e:
        services_status["celery"] = f"import_error: {str(e)}"
        logger.error(f"Failed to import Celery configuration: {e}")

    # Initialize email monitoring service
    try:
        health_check = await email_monitoring_service.health_check()
        if health_check.get("agentmail_available"):
            services_status["email_monitoring"] = "available"
            logger.info("Email monitoring service is available")
        else:
            services_status["email_monitoring"] = f"unavailable: {health_check.get('agentmail_issue', 'unknown')}"
            logger.warning(f"Email monitoring service unavailable: {health_check.get('agentmail_issue')}")
    except Exception as e:
        services_status["email_monitoring"] = f"error: {str(e)}"
        logger.error(f"Failed to initialize email monitoring service: {e}")

    # Log overall services status
    logger.info(f"Background services status: {services_status}")

    # Store services status in app state for health checks
    return services_status


async def _shutdown_background_services():
    """Clean shutdown of background services."""
    logger.info("Shutting down background services...")

    # Celery doesn't need explicit shutdown in this context
    # Workers run in separate processes

    # Email monitoring service cleanup (if needed)
    try:
        # Any cleanup for email monitoring service would go here
        pass
    except Exception as e:
        logger.error(f"Error shutting down email monitoring service: {e}")

    logger.info("Background services shutdown completed")

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
    allow_origins=settings.get_cors_origins(),
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
