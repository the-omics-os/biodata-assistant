from __future__ import annotations

import os
from celery import Celery
from celery.schedules import crontab
from app.config import settings

# Create Celery app
celery_app = Celery("biodata-assistant")

# Configure broker - use Redis if available, fallback to SQLite for development
broker_url = settings.CELERY_BROKER_URL or settings.REDIS_URL
result_backend = settings.CELERY_RESULT_BACKEND or settings.REDIS_URL

if not broker_url:
    # Fallback to SQLite for local development
    broker_url = f"sqla+{settings.DATABASE_URL}"
    result_backend = f"db+{settings.DATABASE_URL}"

celery_app.conf.update(
    broker_url=broker_url,
    result_backend=result_backend,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task discovery
    include=[
        "app.core.tasks.github_prospecting_tasks",
        "app.core.tasks.email_monitoring_tasks",
        "app.core.tasks.outreach_tasks",
    ],

    # Task routing
    task_routes={
        "app.core.tasks.github_prospecting_tasks.*": {"queue": "github_prospecting"},
        "app.core.tasks.email_monitoring_tasks.*": {"queue": "email_monitoring"},
        "app.core.tasks.outreach_tasks.*": {"queue": "outreach"},
    },

    # Worker configuration
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,

    # Task time limits (10 minutes for long-running tasks)
    task_soft_time_limit=600,
    task_time_limit=900,

    # Periodic task schedule - only add enabled tasks
    beat_schedule={},
    beat_schedule_filename="celerybeat-schedule",
)

# Configure periodic tasks based on settings
beat_schedule = {}

if settings.ENABLE_BACKGROUND_TASKS:
    if settings.GITHUB_PROSPECTING_ENABLED:
        beat_schedule["daily-github-prospecting"] = {
            "task": "app.core.tasks.github_prospecting_tasks.run_daily_prospecting",
            "schedule": crontab(hour=settings.GITHUB_PROSPECTING_SCHEDULE_HOUR, minute=0),
            "options": {"queue": "github_prospecting"},
        }

    if settings.EMAIL_MONITORING_ENABLED:
        beat_schedule["email-monitoring"] = {
            "task": "app.core.tasks.email_monitoring_tasks.monitor_inbound_emails",
            "schedule": float(settings.EMAIL_MONITORING_INTERVAL_SECONDS),
            "options": {"queue": "email_monitoring"},
        }

    beat_schedule["process-outreach-queue"] = {
        "task": "app.core.tasks.outreach_tasks.process_outreach_queue",
        "schedule": crontab(minute=f"*/{settings.OUTREACH_PROCESSING_INTERVAL_MINUTES}"),
        "options": {"queue": "outreach"},
    }

# Update the beat schedule
celery_app.conf.beat_schedule = beat_schedule

# Auto-discover tasks
celery_app.autodiscover_tasks()

if __name__ == "__main__":
    celery_app.start()