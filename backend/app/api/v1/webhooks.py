from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, Dict, Any
import hmac
import hashlib
import logging
from datetime import datetime

from app.core.database import get_db
from app.models.database import OutreachRequest
from app.models.enums import OutreachStatus
from app.config import settings
from app.core.services.email_monitoring_service import email_monitoring_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/agentmail/webhook")
async def handle_agentmail_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_agentmail_signature: Optional[str] = Header(default=None),
):
    """
    Handle AgentMail webhook events with optional signature verification.
    Supported event types (primary): message.received, message.delivered, message.bounced
    Also tolerates legacy types: email.sent, email.delivered, email.replied, email.failed
    """
    body = await request.body()

    # Verify webhook signature if configured
    if settings.AGENTMAIL_WEBHOOK_SECRET:
        if not verify_webhook_signature(body, x_agentmail_signature, settings.AGENTMAIL_WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="Invalid AgentMail webhook signature")

    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Invalid JSON payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("event_type") or payload.get("type")

    # Normalize to new-style events
    if event_type == "email.replied":
        event_type = "message.received"
    elif event_type == "email.delivered":
        event_type = "message.delivered"
    elif event_type in ("email.failed", "email.bounced"):
        event_type = "message.bounced"
    elif event_type == "email.sent":
        # treat as delivered if nothing else
        event_type = "message.delivered"

    try:
        if event_type == "message.received":
            handle_message_received(db, payload)
        elif event_type == "message.delivered":
            handle_message_delivered(db, payload)
        elif event_type == "message.bounced":
            handle_message_bounced(db, payload)
        else:
            logger.info(f"Unhandled AgentMail event type: {event_type}")
            return {"status": "ignored", "reason": "unhandled event type", "event_type": event_type}
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")

    return {"status": "ok", "event_type": event_type}


def handle_message_received(db: Session, payload: Dict[str, Any]) -> None:
    """
    Handle incoming email replies.
    Attempt to map to outreach via thread_id, message_id, or metadata.dataset_id.
    """
    message = payload.get("message", payload) or {}
    metadata = message.get("metadata", payload.get("metadata", {})) or {}

    thread_id = message.get("thread_id") or payload.get("thread_id")
    message_id = message.get("id") or payload.get("message_id")
    dataset_id = metadata.get("dataset_id")

    outreach = None
    if thread_id:
        outreach = db.query(OutreachRequest).filter(OutreachRequest.thread_id == str(thread_id)).first()
    if not outreach and message_id:
        outreach = db.query(OutreachRequest).filter(OutreachRequest.message_id == str(message_id)).first()
    if not outreach and dataset_id:
        outreach = db.query(OutreachRequest).filter(OutreachRequest.dataset_id == str(dataset_id)).first()

    if not outreach:
        logger.warning("Cannot map AgentMail reply to an outreach request")
        return

    outreach.status = OutreachStatus.REPLIED.value
    received_at = message.get("received_at") or payload.get("received_at")
    try:
        outreach.replied_at = datetime.fromisoformat(received_at) if received_at else datetime.utcnow()
    except Exception:
        outreach.replied_at = datetime.utcnow()

    # If attachments present, require approval
    attachments = message.get("attachments") or []
    if attachments:
        outreach.approval_required = True

    db.commit()

    # Provenance
    try:
        from app.core.utils.provenance import log_provenance as log_prov
        sender = message.get("from") or message.get("from_email")
        log_prov_sync(db, actor="webhook_receiver", action="reply_received", details={
            "from": sender, "has_attachments": bool(attachments), "outreach_id": outreach.id
        })
    except Exception:
        pass


def handle_message_delivered(db: Session, payload: Dict[str, Any]) -> None:
    """Update outreach status to delivered."""
    message_id = payload.get("message_id") or payload.get("id")
    thread_id = payload.get("thread_id")

    outreach = None
    if message_id:
        outreach = db.query(OutreachRequest).filter(OutreachRequest.message_id == str(message_id)).first()
    if not outreach and thread_id:
        outreach = db.query(OutreachRequest).filter(OutreachRequest.thread_id == str(thread_id)).first()

    if not outreach:
        logger.info("Delivery event received but outreach not found")
        return

    outreach.status = OutreachStatus.DELIVERED.value
    db.commit()


def handle_message_bounced(db: Session, payload: Dict[str, Any]) -> None:
    """Handle bounced/failed emails."""
    message_id = payload.get("message_id") or payload.get("id")
    reason = payload.get("reason") or payload.get("error") or "unknown"

    outreach = None
    if message_id:
        outreach = db.query(OutreachRequest).filter(OutreachRequest.message_id == str(message_id)).first()

    if not outreach:
        logger.info("Bounce event received but outreach not found")
        return

    outreach.status = OutreachStatus.CLOSED.value  # or keep previous; CLOSED to stop retry loop
    db.commit()

    try:
        log_prov_sync(db, actor="webhook_receiver", action="email_bounced", details={"reason": reason, "outreach_id": outreach.id})
    except Exception:
        pass


def verify_webhook_signature(body: bytes, signature: Optional[str], secret: str) -> bool:
    """Verify HMAC-SHA256 signature."""
    if not signature:
        return False
    try:
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


def log_prov_sync(db: Session, actor: str, action: str, details: Optional[Dict[str, Any]] = None) -> None:
    """Synchronous provenance log helper to avoid creating new sessions inside webhook path."""
    try:
        from app.core.utils.provenance import log_provenance
        # utils.provenance.log_provenance is async; call via loop if available, else best-effort swallow.
        import asyncio
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            loop.create_task(log_provenance(actor=actor, action=action, details=details or {}))  # fire-and-forget
        else:
            asyncio.run(log_provenance(actor=actor, action=action, details=details or {}))
    except Exception:
        pass


@router.get("/health")
async def webhook_health():
    """Health check for webhook endpoints."""
    return {"status": "healthy", "service": "webhooks"}


@router.get("/email-monitoring/health")
async def email_monitoring_health():
    """Health check for email monitoring service."""
    health_status = await email_monitoring_service.health_check()
    return health_status


@router.post("/email-monitoring/check")
async def trigger_email_monitoring_check():
    """Manually trigger an email monitoring check."""
    result = await email_monitoring_service.manual_check()
    return result


@router.post("/email-monitoring/check-missed")
async def trigger_missed_replies_check():
    """Manually trigger a check for missed email replies."""
    result = await email_monitoring_service.check_missed_replies()
    return result


@router.get("/email-monitoring/stats")
async def get_email_monitoring_stats(
    days: int = Query(7, ge=1, le=90, description="Number of days for statistics")
):
    """Get email monitoring statistics."""
    stats = await email_monitoring_service.get_monitoring_statistics(days=days)
    return stats


@router.get("/email-monitoring/config")
async def get_email_monitoring_config():
    """Get current email monitoring configuration."""
    config = await email_monitoring_service.configure_monitoring()
    return config


@router.post("/email-monitoring/test-connection")
async def test_agentmail_connection():
    """Test the connection to AgentMail service."""
    result = await email_monitoring_service.test_agentmail_connection()
    return result
