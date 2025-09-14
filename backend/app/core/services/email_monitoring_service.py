from __future__ import annotations

import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from app.config import settings
from app.core.integrations.agentmail_client import AgentMailClient
from app.core.tasks.email_monitoring_tasks import monitor_inbound_emails, process_missed_replies
from app.core.utils.provenance import log_provenance
from app.models.database import OutreachRequest
from app.models.enums import OutreachStatus
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


class EmailMonitoringService:
    """
    Service class to manage continuous email monitoring.
    Provides health checks, manual triggers, and status monitoring.
    """

    def __init__(self):
        self.client = AgentMailClient()
        self.is_running = False
        self.last_check = None
        self.stats = {
            "total_checks": 0,
            "messages_processed": 0,
            "errors": 0,
            "last_error": None,
        }

    async def health_check(self) -> Dict[str, Any]:
        """
        Check the health of the email monitoring service.
        Returns status and configuration information.
        """
        status = {
            "service_enabled": settings.EMAIL_MONITORING_ENABLED,
            "agentmail_available": self.client.enabled,
            "check_interval_seconds": settings.EMAIL_MONITORING_INTERVAL_SECONDS,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "stats": self.stats.copy(),
        }

        if not self.client.enabled:
            status["agentmail_issue"] = self.client.disabled_reason

        # Check if monitoring is actually working by looking at recent activity
        session = SessionLocal()
        try:
            # Count recent email monitoring activity
            recent_cutoff = datetime.utcnow() - timedelta(hours=1)

            # Check for recent provenance logs from email monitoring
            from app.models.database import Provenance
            recent_monitoring = session.query(Provenance).filter(
                Provenance.actor == "email_monitoring_task",
                Provenance.created_at >= recent_cutoff
            ).count()

            status["recent_activity"] = {
                "monitoring_logs_last_hour": recent_monitoring,
                "appears_active": recent_monitoring > 0,
            }

        except Exception as e:
            logger.error(f"Failed to check recent activity: {e}")
            status["recent_activity"] = {"error": str(e)}
        finally:
            session.close()

        return status

    async def manual_check(self) -> Dict[str, Any]:
        """
        Manually trigger an email monitoring check.
        Useful for testing and immediate processing.
        """
        if not settings.EMAIL_MONITORING_ENABLED:
            return {"error": "Email monitoring is disabled in settings"}

        if not self.client.enabled:
            return {"error": f"AgentMail client unavailable: {self.client.disabled_reason}"}

        try:
            # Log the manual trigger
            await log_provenance(
                actor="email_monitoring_service",
                action="manual_check_triggered",
                details={"timestamp": datetime.utcnow().isoformat()},
            )

            # Trigger the monitoring task directly
            result = monitor_inbound_emails.delay()

            # Update our tracking
            self.last_check = datetime.utcnow()
            self.stats["total_checks"] += 1

            return {
                "status": "triggered",
                "task_id": str(result.id) if result else None,
                "timestamp": self.last_check.isoformat(),
            }

        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            logger.error(f"Manual email monitoring check failed: {e}")

            await log_provenance(
                actor="email_monitoring_service",
                action="manual_check_failed",
                details={"error": str(e)},
            )

            return {"error": str(e)}

    async def check_missed_replies(self) -> Dict[str, Any]:
        """
        Manually trigger a check for missed email replies.
        This is a more thorough check that runs less frequently.
        """
        try:
            await log_provenance(
                actor="email_monitoring_service",
                action="missed_replies_check_triggered",
                details={"timestamp": datetime.utcnow().isoformat()},
            )

            # Trigger the missed replies task
            result = process_missed_replies.delay()

            return {
                "status": "triggered",
                "task_id": str(result.id) if result else None,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Missed replies check failed: {e}")
            return {"error": str(e)}

    async def get_monitoring_statistics(self, days: int = 7) -> Dict[str, Any]:
        """
        Get email monitoring statistics for the specified period.

        Args:
            days: Number of days to include in statistics
        """
        session = SessionLocal()
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # Get email-related statistics
            stats = {
                "period_days": days,
                "service_stats": self.stats.copy(),
            }

            # Count outreach requests by status that have email activity
            outreach_with_activity = session.query(OutreachRequest).filter(
                OutreachRequest.created_at >= cutoff_date
            ).all()

            email_stats = {
                "total_outreach": len(outreach_with_activity),
                "sent": len([o for o in outreach_with_activity if o.sent_at]),
                "replied": len([o for o in outreach_with_activity if o.replied_at]),
                "reply_rate": 0,
            }

            # Calculate reply rate
            sent_count = email_stats["sent"]
            if sent_count > 0:
                email_stats["reply_rate"] = email_stats["replied"] / sent_count

            stats["email_stats"] = email_stats

            # Get monitoring activity from provenance
            from app.models.database import Provenance
            monitoring_logs = session.query(Provenance).filter(
                Provenance.actor == "email_monitoring_task",
                Provenance.created_at >= cutoff_date
            ).all()

            monitoring_activity = {
                "total_monitoring_runs": len([log for log in monitoring_logs if log.action == "email_monitoring_completed"]),
                "total_errors": len([log for log in monitoring_logs if log.action == "email_monitoring_failed"]),
                "replies_processed": len([log for log in monitoring_logs if log.action == "email_reply_processed"]),
            }

            stats["monitoring_activity"] = monitoring_activity

            return stats

        except Exception as e:
            logger.error(f"Failed to get monitoring statistics: {e}")
            return {"error": str(e)}
        finally:
            session.close()

    async def configure_monitoring(self, **kwargs) -> Dict[str, Any]:
        """
        Update monitoring configuration (if supported in the future).
        Currently returns current configuration.
        """
        return {
            "current_config": {
                "enabled": settings.EMAIL_MONITORING_ENABLED,
                "interval_seconds": settings.EMAIL_MONITORING_INTERVAL_SECONDS,
                "agentmail_available": self.client.enabled,
            },
            "note": "Configuration changes require environment variable updates and service restart"
        }

    async def test_agentmail_connection(self) -> Dict[str, Any]:
        """
        Test the AgentMail connection and basic functionality.
        """
        if not self.client.enabled:
            return {
                "success": False,
                "error": self.client.disabled_reason,
            }

        try:
            # Try to list messages as a connection test
            messages = await self.client.list_messages()

            return {
                "success": True,
                "connection_status": "active",
                "messages_available": len(messages),
                "test_timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"AgentMail connection test failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "test_timestamp": datetime.utcnow().isoformat(),
            }


# Global service instance
email_monitoring_service = EmailMonitoringService()