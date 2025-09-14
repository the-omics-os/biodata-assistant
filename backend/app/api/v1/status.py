from fastapi import APIRouter
from datetime import datetime
from app.models.schemas import HealthResponse
from app.config import settings

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version=settings.VERSION,
        timestamp=datetime.utcnow()
    )

@router.get("/status")
async def api_status():
    """API status and information endpoint."""
    return {
        "status": "online",
        "version": settings.VERSION,
        "app_name": settings.APP_NAME,
        "timestamp": datetime.utcnow(),
        "debug_mode": settings.DEBUG
    }
