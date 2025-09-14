"""
Service layer for the biodata-assistant application.

This package contains service classes that provide high-level interfaces
for managing background processes and system monitoring.
"""

from .email_monitoring_service import EmailMonitoringService, email_monitoring_service

__all__ = [
    "EmailMonitoringService",
    "email_monitoring_service",
]