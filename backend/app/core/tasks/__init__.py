"""
Background task modules for the biodata-assistant application.

This package contains Celery tasks for:
- GitHub issues prospecting and lead generation
- Email monitoring and response handling
- Automated outreach workflows
- Task monitoring and reporting
"""

# Make tasks easily importable
from .github_prospecting_tasks import (
    run_daily_prospecting,
    prospect_github_repos,
    process_single_repository,
)

from .email_monitoring_tasks import (
    monitor_inbound_emails,
    process_email_reply,
    check_agentmail_messages,
)

from .outreach_tasks import (
    process_outreach_queue,
    send_automated_outreach,
    send_single_outreach,
)

__all__ = [
    # GitHub prospecting tasks
    "run_daily_prospecting",
    "prospect_github_repos",
    "process_single_repository",

    # Email monitoring tasks
    "monitor_inbound_emails",
    "process_email_reply",
    "check_agentmail_messages",

    # Outreach tasks
    "process_outreach_queue",
    "send_automated_outreach",
    "send_single_outreach",
]