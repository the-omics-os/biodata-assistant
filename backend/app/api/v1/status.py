from fastapi import APIRouter
from datetime import datetime
from app.models.schemas import HealthResponse
from app.config import settings
from app.core.services.email_monitoring_service import email_monitoring_service

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


@router.get("/status/detailed")
async def detailed_status():
    """Detailed status including background services."""
    status = {
        "api": {
            "status": "online",
            "version": settings.VERSION,
            "app_name": settings.APP_NAME,
            "timestamp": datetime.utcnow(),
            "debug_mode": settings.DEBUG,
        },
        "configuration": {
            "background_tasks_enabled": settings.ENABLE_BACKGROUND_TASKS,
            "github_prospecting_enabled": settings.GITHUB_PROSPECTING_ENABLED,
            "email_monitoring_enabled": settings.EMAIL_MONITORING_ENABLED,
            "automated_outreach_enabled": settings.AUTOMATED_OUTREACH_ENABLED,
        }
    }

    # Get background services status
    try:
        # Check Celery status
        if settings.ENABLE_BACKGROUND_TASKS:
            try:
                from app.core.celery_app import celery_app
                inspect = celery_app.control.inspect()
                active_workers = inspect.active()

                status["background_services"] = {
                    "celery": {
                        "status": "connected" if active_workers else "no_workers",
                        "active_workers": list(active_workers.keys()) if active_workers else [],
                        "broker_url": celery_app.conf.broker_url,
                    }
                }
            except Exception as e:
                status["background_services"] = {
                    "celery": {
                        "status": "error",
                        "error": str(e),
                    }
                }
        else:
            status["background_services"] = {
                "celery": {"status": "disabled"}
            }

        # Get email monitoring status
        email_health = await email_monitoring_service.health_check()
        status["background_services"]["email_monitoring"] = email_health

    except Exception as e:
        status["background_services"] = {
            "error": f"Failed to check background services: {str(e)}"
        }

    return status


@router.get("/status/background-tasks")
async def background_tasks_status():
    """Specific status for background task system."""
    if not settings.ENABLE_BACKGROUND_TASKS:
        return {
            "enabled": False,
            "message": "Background tasks are disabled in configuration"
        }

    try:
        from app.core.celery_app import celery_app

        # Get Celery inspection
        inspect = celery_app.control.inspect()

        # Get worker information
        active_workers = inspect.active() or {}
        registered_tasks = inspect.registered() or {}
        scheduled_tasks = inspect.scheduled() or {}

        # Get beat schedule info
        beat_schedule = celery_app.conf.beat_schedule or {}

        return {
            "enabled": True,
            "broker_url": celery_app.conf.broker_url,
            "workers": {
                "active_count": len(active_workers),
                "active_workers": list(active_workers.keys()),
                "total_active_tasks": sum(len(tasks) for tasks in active_workers.values()),
            },
            "tasks": {
                "registered_count": sum(len(tasks) for tasks in registered_tasks.values()) if registered_tasks else 0,
                "scheduled_count": sum(len(tasks) for tasks in scheduled_tasks.values()) if scheduled_tasks else 0,
            },
            "schedule": {
                "periodic_tasks_count": len(beat_schedule),
                "periodic_tasks": list(beat_schedule.keys()),
            },
            "configuration": {
                "github_prospecting_enabled": settings.GITHUB_PROSPECTING_ENABLED,
                "email_monitoring_enabled": settings.EMAIL_MONITORING_ENABLED,
                "automated_outreach_enabled": settings.AUTOMATED_OUTREACH_ENABLED,
            }
        }

    except Exception as e:
        return {
            "enabled": True,
            "error": str(e),
            "message": "Failed to connect to Celery broker or workers"
        }
