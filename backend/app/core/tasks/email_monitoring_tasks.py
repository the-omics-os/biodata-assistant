from __future__ import annotations

import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from celery import current_task
from app.core.celery_app import celery_app
from app.config import settings
from app.core.integrations.agentmail_client import AgentMailClient
from app.core.utils.provenance import log_provenance
from app.models.database import OutreachRequest, Lead
from app.models.enums import OutreachStatus, LeadStage
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def monitor_inbound_emails(self):
    """
    Periodic task to monitor inbound emails from AgentMail.
    Runs every 30 seconds (configurable) to check for new messages.
    """
    if not settings.EMAIL_MONITORING_ENABLED:
        logger.debug("Email monitoring is disabled, skipping task")
        return {"status": "disabled"}

    logger.debug("Starting email monitoring check")

    try:
        result = asyncio.run(_check_and_process_emails())
        logger.debug(f"Email monitoring completed: {result}")
        return result

    except Exception as exc:
        logger.error(f"Email monitoring task failed: {exc}")
        # Don't retry for monitoring tasks - just log and continue
        return {"status": "error", "message": str(exc)}


@celery_app.task(bind=True, max_retries=3)
def process_email_reply(self, message_data: Dict[str, Any], outreach_id: Optional[str] = None):
    """
    Process a specific email reply and update the corresponding outreach record.

    Args:
        message_data: Email message data from AgentMail
        outreach_id: Optional outreach request ID if known
    """
    logger.info(f"Processing email reply for outreach: {outreach_id}")

    session = SessionLocal()
    try:
        result = asyncio.run(_process_single_email_reply(message_data, outreach_id, session))
        session.commit()

        logger.info(f"Email reply processed successfully: {result}")
        return result

    except Exception as exc:
        session.rollback()
        logger.error(f"Failed to process email reply: {exc}")

        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            retry_delay = 30 * (2 ** self.request.retries)  # 30s, 60s, 120s
            logger.info(f"Retrying email processing in {retry_delay} seconds")
            raise self.retry(countdown=retry_delay, exc=exc)

        raise
    finally:
        session.close()


@celery_app.task
def check_agentmail_messages(inbox_id: Optional[str] = None):
    """
    Check for new messages in AgentMail inboxes.
    Can be called manually or as part of monitoring workflow.

    Args:
        inbox_id: Optional specific inbox to check (default: all inboxes)
    """
    logger.info(f"Checking AgentMail messages for inbox: {inbox_id or 'all'}")

    try:
        result = asyncio.run(_fetch_agentmail_messages(inbox_id))
        logger.info(f"AgentMail check completed: {result['messages_checked']} messages checked")
        return result

    except Exception as exc:
        logger.error(f"Failed to check AgentMail messages: {exc}")
        return {"status": "error", "message": str(exc), "messages_checked": 0}


async def _check_and_process_emails() -> Dict[str, Any]:
    """
    Core email monitoring workflow.
    Checks AgentMail for new messages and processes them.
    """
    start_time = datetime.utcnow()

    # Log monitoring start
    await log_provenance(
        actor="email_monitoring_task",
        action="email_monitoring_started",
        details={"timestamp": start_time.isoformat()},
    )

    client = AgentMailClient()

    if not client.enabled:
        logger.debug(f"AgentMail client disabled: {client.disabled_reason}")
        return {
            "status": "disabled",
            "reason": client.disabled_reason,
            "messages_processed": 0,
        }

    try:
        # Get all messages from AgentMail
        messages = await client.list_messages()

        processed_count = 0
        error_count = 0
        new_replies = []

        session = SessionLocal()
        try:
            for message in messages:
                try:
                    # Check if this message represents a new reply to an outreach
                    result = await _process_single_email_reply(message, None, session)
                    if result.get("processed"):
                        processed_count += 1
                        new_replies.append(result)
                except Exception as e:
                    logger.error(f"Failed to process message {message.get('id')}: {e}")
                    error_count += 1

            session.commit()

        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        # Calculate processing time
        end_time = datetime.utcnow()
        processing_time = (end_time - start_time).total_seconds()

        result = {
            "status": "completed",
            "messages_checked": len(messages),
            "messages_processed": processed_count,
            "errors": error_count,
            "new_replies": len(new_replies),
            "processing_time_seconds": processing_time,
            "completed_at": end_time.isoformat(),
        }

        # Log successful monitoring
        await log_provenance(
            actor="email_monitoring_task",
            action="email_monitoring_completed",
            details=result,
        )

        return result

    except Exception as exc:
        # Log monitoring failure
        await log_provenance(
            actor="email_monitoring_task",
            action="email_monitoring_failed",
            details={"error": str(exc)},
        )
        raise


async def _process_single_email_reply(
    message_data: Dict[str, Any],
    outreach_id: Optional[str],
    session: Any
) -> Dict[str, Any]:
    """
    Process a single email message and update the corresponding outreach record.

    Args:
        message_data: Email message data
        outreach_id: Optional outreach ID if known
        session: Database session

    Returns:
        Dict with processing results
    """
    message_id = message_data.get("id")
    from_email = message_data.get("from")
    subject = message_data.get("subject", "")
    received_at_str = message_data.get("received_at")

    # Parse received timestamp
    received_at = datetime.utcnow()
    if received_at_str:
        try:
            received_at = datetime.fromisoformat(received_at_str.replace("Z", "+00:00"))
        except Exception:
            pass

    # Find corresponding outreach request
    outreach = None

    if outreach_id:
        outreach = session.query(OutreachRequest).filter_by(id=outreach_id).first()

    # If not found by ID, try to find by message context
    if not outreach and message_id:
        outreach = session.query(OutreachRequest).filter_by(message_id=str(message_id)).first()

    # Try to find by thread context or email address
    if not outreach and from_email:
        outreach = session.query(OutreachRequest).filter_by(contact_email=from_email).order_by(
            OutreachRequest.sent_at.desc()
        ).first()

    if not outreach:
        logger.debug(f"No matching outreach found for message {message_id} from {from_email}")
        return {"processed": False, "reason": "no_matching_outreach"}

    # Check if this is actually a new reply (not already processed)
    if outreach.status == OutreachStatus.REPLIED.value and outreach.replied_at:
        # Check if this is a newer reply
        if outreach.replied_at >= received_at:
            logger.debug(f"Reply already processed for outreach {outreach.id}")
            return {"processed": False, "reason": "already_processed"}

    # Update outreach status
    old_status = outreach.status
    outreach.status = OutreachStatus.REPLIED.value
    outreach.replied_at = received_at

    # Update corresponding lead if it exists
    lead = session.query(Lead).filter_by(email=outreach.contact_email).first()
    if lead:
        # Move lead to "replied" stage if it's in an earlier stage
        if lead.stage in [LeadStage.NEW.value, LeadStage.ENRICHED.value, LeadStage.CONTACTED.value]:
            lead.stage = LeadStage.REPLIED.value

    # Log the reply processing
    await log_provenance(
        actor="email_monitoring_task",
        action="email_reply_processed",
        resource_type="outreach",
        resource_id=outreach.id,
        details={
            "message_id": message_id,
            "from_email": from_email,
            "subject": subject,
            "old_status": old_status,
            "new_status": outreach.status,
            "received_at": received_at.isoformat(),
        },
    )

    return {
        "processed": True,
        "outreach_id": outreach.id,
        "old_status": old_status,
        "new_status": outreach.status,
        "from_email": from_email,
        "subject": subject,
    }


async def _fetch_agentmail_messages(inbox_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch messages from AgentMail API.

    Args:
        inbox_id: Optional inbox ID to filter messages

    Returns:
        Dict with fetched messages and statistics
    """
    client = AgentMailClient()

    if not client.enabled:
        return {
            "status": "disabled",
            "reason": client.disabled_reason,
            "messages_checked": 0,
        }

    try:
        messages = await client.list_messages(inbox_id=inbox_id)

        return {
            "status": "success",
            "messages_checked": len(messages),
            "messages": messages,
            "inbox_id": inbox_id,
        }

    except Exception as exc:
        logger.error(f"Failed to fetch AgentMail messages: {exc}")
        return {
            "status": "error",
            "message": str(exc),
            "messages_checked": 0,
        }


@celery_app.task
def process_missed_replies():
    """
    Periodic task to catch any missed email replies.
    Runs less frequently to catch replies that might have been missed by real-time monitoring.
    """
    logger.info("Starting missed replies processing")

    session = SessionLocal()
    try:
        # Find outreach requests that were sent but haven't been marked as replied
        # and check if there are any replies in AgentMail
        cutoff_time = datetime.utcnow() - timedelta(hours=24)  # Check last 24 hours

        pending_outreach = session.query(OutreachRequest).filter(
            OutreachRequest.status.in_([OutreachStatus.SENT.value, OutreachStatus.DELIVERED.value]),
            OutreachRequest.sent_at >= cutoff_time
        ).all()

        processed_count = 0

        for outreach in pending_outreach:
            try:
                # Use the regular monitoring task to check for replies
                result = asyncio.run(_check_specific_outreach_replies(outreach, session))
                if result.get("reply_found"):
                    processed_count += 1

            except Exception as e:
                logger.error(f"Failed to check replies for outreach {outreach.id}: {e}")

        session.commit()

        logger.info(f"Missed replies processing completed: {processed_count} replies found")
        return {
            "status": "completed",
            "outreach_checked": len(pending_outreach),
            "replies_found": processed_count,
        }

    except Exception as exc:
        session.rollback()
        logger.error(f"Missed replies processing failed: {exc}")
        raise
    finally:
        session.close()


async def _check_specific_outreach_replies(outreach: OutreachRequest, session: Any) -> Dict[str, Any]:
    """
    Check for replies to a specific outreach request.

    Args:
        outreach: OutreachRequest database object
        session: Database session

    Returns:
        Dict indicating if a reply was found and processed
    """
    client = AgentMailClient()

    if not client.enabled:
        return {"reply_found": False, "reason": "agentmail_disabled"}

    try:
        # Get all messages and look for replies to this outreach
        messages = await client.list_messages()

        for message in messages:
            # Try to match this message to the outreach
            from_email = message.get("from", "").lower()
            contact_email = outreach.contact_email.lower()

            if from_email == contact_email:
                # Check if this message is newer than when we sent the outreach
                received_at_str = message.get("received_at")
                if received_at_str and outreach.sent_at:
                    try:
                        received_at = datetime.fromisoformat(received_at_str.replace("Z", "+00:00"))
                        if received_at > outreach.sent_at:
                            # This looks like a reply - process it
                            result = await _process_single_email_reply(message, outreach.id, session)
                            if result.get("processed"):
                                return {"reply_found": True, "outreach_id": outreach.id}
                    except Exception:
                        pass

        return {"reply_found": False}

    except Exception as exc:
        logger.error(f"Failed to check replies for outreach {outreach.id}: {exc}")
        return {"reply_found": False, "error": str(exc)}


@celery_app.task
def cleanup_old_email_logs():
    """
    Cleanup task to remove old email monitoring logs from provenance table.
    Runs weekly to prevent database bloat.
    """
    logger.info("Starting cleanup of old email monitoring logs")

    session = SessionLocal()
    try:
        # Import here to avoid circular imports
        from app.models.database import Provenance

        # Delete email monitoring logs older than 7 days
        cutoff_date = datetime.utcnow() - timedelta(days=7)

        deleted_count = session.query(Provenance).filter(
            Provenance.actor == "email_monitoring_task",
            Provenance.created_at < cutoff_date
        ).delete()

        session.commit()

        logger.info(f"Cleaned up {deleted_count} old email monitoring logs")
        return {"deleted_logs": deleted_count, "cutoff_date": cutoff_date.isoformat()}

    except Exception as exc:
        session.rollback()
        logger.error(f"Failed to cleanup old email logs: {exc}")
        raise
    finally:
        session.close()