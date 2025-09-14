from __future__ import annotations

import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from celery import current_task
from app.core.celery_app import celery_app
from app.config import settings
from app.core.agents.email_agent import send_product_invite_direct, ProductInviteParams
from app.core.utils.provenance import log_provenance
from app.models.database import OutreachRequest, Lead
from app.models.enums import OutreachStatus, LeadStage, TaskType, TaskStatus
from app.utils.personas import select_persona
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def process_outreach_queue(self):
    """
    Periodic task to process queued outreach requests.
    Runs every 5 minutes to send approved outreach emails.
    """
    logger.info("Processing outreach queue")

    session = SessionLocal()
    try:
        # Find queued outreach requests that are ready to send
        queued_outreach = session.query(OutreachRequest).filter(
            OutreachRequest.status == OutreachStatus.QUEUED.value
        ).order_by(OutreachRequest.created_at.asc()).limit(10).all()  # Process 10 at a time

        if not queued_outreach:
            logger.debug("No queued outreach requests found")
            return {"status": "no_work", "processed": 0}

        processed_count = 0
        error_count = 0
        results = []

        for outreach in queued_outreach:
            try:
                # Check if this outreach requires approval and hasn't been approved
                if outreach.approval_required and not outreach.approved_at:
                    logger.debug(f"Outreach {outreach.id} requires approval, skipping")
                    continue

                # Send the outreach email
                result = asyncio.run(_send_outreach_email(outreach, session))

                if result.get("success"):
                    processed_count += 1
                    logger.info(f"Successfully sent outreach {outreach.id}")
                else:
                    error_count += 1
                    logger.error(f"Failed to send outreach {outreach.id}: {result.get('error')}")

                results.append(result)

            except Exception as e:
                error_count += 1
                logger.error(f"Failed to process outreach {outreach.id}: {e}")
                results.append({"outreach_id": outreach.id, "success": False, "error": str(e)})

        session.commit()

        logger.info(f"Outreach queue processing completed: {processed_count} sent, {error_count} errors")
        return {
            "status": "completed",
            "processed": processed_count,
            "errors": error_count,
            "results": results,
        }

    except Exception as exc:
        session.rollback()
        logger.error(f"Outreach queue processing failed: {exc}")
        raise
    finally:
        session.close()


@celery_app.task(bind=True, max_retries=3)
def send_automated_outreach(self, lead_id: str, template_type: str = "product_invite"):
    """
    Send automated outreach email to a specific lead.

    Args:
        lead_id: Database ID of the lead
        template_type: Type of email template to use
    """
    logger.info(f"Sending automated outreach to lead {lead_id}")

    session = SessionLocal()
    try:
        # Get the lead from database
        lead = session.query(Lead).filter_by(id=lead_id).first()
        if not lead:
            logger.error(f"Lead {lead_id} not found")
            return {"success": False, "error": "Lead not found"}

        if not lead.email:
            logger.error(f"Lead {lead_id} has no email address")
            return {"success": False, "error": "No email address"}

        # Check if we've already sent outreach to this lead recently
        recent_cutoff = datetime.utcnow() - timedelta(days=7)
        existing_outreach = session.query(OutreachRequest).filter(
            OutreachRequest.contact_email == lead.email,
            OutreachRequest.created_at >= recent_cutoff
        ).first()

        if existing_outreach:
            logger.info(f"Recent outreach already exists for lead {lead_id}, skipping")
            return {"success": False, "error": "Recent outreach already exists", "skip": True}

        # Select appropriate persona for this lead
        persona = select_persona({
            "repo": lead.repo,
            "issue_title": lead.issue_title,
            "user_login": lead.user_login,
        })

        # Create outreach request record
        outreach = OutreachRequest(
            dataset_id="",  # Not applicable for GitHub leads
            requester_email=persona.from_email,
            requester_name=persona.name,
            contact_email=lead.email,
            contact_name=lead.user_login,
            status=OutreachStatus.DRAFT.value,
            email_subject="",  # Will be set by template
            email_body="",     # Will be set by template
            approval_required=not settings.AUTOMATED_OUTREACH_ENABLED,
        )

        session.add(outreach)
        session.flush()  # Get the ID

        # Send the outreach
        result = asyncio.run(_send_lead_outreach(lead, persona, outreach, session))

        # Update lead stage
        if result.get("success"):
            lead.stage = LeadStage.CONTACTED.value

        session.commit()

        logger.info(f"Automated outreach completed for lead {lead_id}: {result}")
        return result

    except Exception as exc:
        session.rollback()
        logger.error(f"Automated outreach failed for lead {lead_id}: {exc}")

        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            retry_delay = 300 * (2 ** self.request.retries)  # 5m, 10m, 20m
            logger.info(f"Retrying automated outreach in {retry_delay} seconds")
            raise self.retry(countdown=retry_delay, exc=exc)

        return {"success": False, "error": str(exc)}
    finally:
        session.close()


@celery_app.task(bind=True, max_retries=2)
def send_single_outreach(self, outreach_id: str):
    """
    Send a single outreach email by ID.
    Used for manual triggering of specific outreach requests.

    Args:
        outreach_id: Database ID of the outreach request
    """
    logger.info(f"Sending single outreach {outreach_id}")

    session = SessionLocal()
    try:
        outreach = session.query(OutreachRequest).filter_by(id=outreach_id).first()
        if not outreach:
            logger.error(f"Outreach {outreach_id} not found")
            return {"success": False, "error": "Outreach not found"}

        result = asyncio.run(_send_outreach_email(outreach, session))
        session.commit()

        logger.info(f"Single outreach completed for {outreach_id}: {result}")
        return result

    except Exception as exc:
        session.rollback()
        logger.error(f"Single outreach failed for {outreach_id}: {exc}")

        # Retry with backoff
        if self.request.retries < self.max_retries:
            retry_delay = 60 * (2 ** self.request.retries)  # 1m, 2m
            logger.info(f"Retrying single outreach in {retry_delay} seconds")
            raise self.retry(countdown=retry_delay, exc=exc)

        return {"success": False, "error": str(exc)}
    finally:
        session.close()


async def _send_outreach_email(outreach: OutreachRequest, session: Any) -> Dict[str, Any]:
    """
    Core function to send an outreach email using the email agent.

    Args:
        outreach: OutreachRequest database object
        session: Database session

    Returns:
        Dict with sending results
    """
    try:
        # Update status to sending
        outreach.status = OutreachStatus.SENDING.value
        session.commit()

        # Log outreach attempt
        await log_provenance(
            actor="outreach_task",
            action="outreach_sending_started",
            resource_type="outreach",
            resource_id=outreach.id,
            details={
                "contact_email": outreach.contact_email,
                "requester_email": outreach.requester_email,
            },
        )

        # For GitHub leads, we need to use the product invite flow
        # Check if this is a GitHub lead by looking for associated lead
        lead = session.query(Lead).filter_by(email=outreach.contact_email).first()

        if lead:
            # This is a GitHub lead - use product invite
            persona = select_persona({
                "repo": lead.repo,
                "issue_title": lead.issue_title,
                "user_login": lead.user_login,
            })

            result = await _send_lead_outreach(lead, persona, outreach, session)
        else:
            # This is a regular data request outreach - use the existing flow
            # TODO: Implement data request outreach flow
            result = {"success": False, "error": "Data request outreach not yet implemented"}

        # Update outreach status based on result
        if result.get("success"):
            outreach.status = OutreachStatus.SENT.value
            outreach.sent_at = datetime.utcnow()
            outreach.message_id = result.get("message_id")
            outreach.thread_id = result.get("thread_id")

            # Log successful send
            await log_provenance(
                actor="outreach_task",
                action="outreach_sent",
                resource_type="outreach",
                resource_id=outreach.id,
                details={
                    "message_id": result.get("message_id"),
                    "contact_email": outreach.contact_email,
                },
            )
        else:
            outreach.status = OutreachStatus.FAILED.value
            error_msg = result.get("error_message") or result.get("error", "Unknown error")

            # Log failed send
            await log_provenance(
                actor="outreach_task",
                action="outreach_failed",
                resource_type="outreach",
                resource_id=outreach.id,
                details={
                    "error": error_msg,
                    "contact_email": outreach.contact_email,
                },
            )

        return result

    except Exception as exc:
        # Update status to failed
        outreach.status = OutreachStatus.FAILED.value

        # Log failure
        await log_provenance(
            actor="outreach_task",
            action="outreach_failed",
            resource_type="outreach",
            resource_id=outreach.id,
            details={"error": str(exc)},
        )

        logger.error(f"Failed to send outreach {outreach.id}: {exc}")
        return {"success": False, "error": str(exc)}


async def _send_lead_outreach(
    lead: Lead,
    persona: Any,
    outreach: OutreachRequest,
    session: Any
) -> Dict[str, Any]:
    """
    Send outreach email to a GitHub lead using the product invite flow.

    Args:
        lead: Lead database object
        persona: Selected persona for the outreach
        outreach: OutreachRequest database object
        session: Database session

    Returns:
        Dict with send results
    """
    try:
        # Prepare recipient name (clean up GitHub username)
        recipient_name = lead.user_login.replace("_", " ").replace("-", " ").title()

        # Create product invite parameters
        params = ProductInviteParams(
            lead_id=lead.id,
            repo=lead.repo,
            issue_title=lead.issue_title,
            recipient_name=recipient_name,
            recipient_email=lead.email,
            persona_name=persona.name,
            persona_title=persona.title,
            persona_from_email=persona.from_email,
            message_style="casual",
        )

        # Send using the email agent
        result = await send_product_invite_direct(params)

        # Update outreach record with template content if successful
        if result.get("success"):
            # The email agent doesn't return the template content, so we'll generate it for logging
            from app.utils.email_templates import generate_email_template

            template = generate_email_template(
                template_type="product_invite",
                persona_name=persona.name,
                persona_title=persona.title,
                repo=lead.repo,
                issue_title=lead.issue_title,
                recipient_name=recipient_name,
                message_style="casual",
            )

            outreach.email_subject = template.get("subject", "")
            outreach.email_body = template.get("body", "")
            outreach.requester_email = persona.from_email
            outreach.requester_name = persona.name

        return result

    except Exception as exc:
        logger.error(f"Failed to send lead outreach for {lead.id}: {exc}")
        return {"success": False, "error": str(exc)}


@celery_app.task
def schedule_automated_outreach():
    """
    Task to schedule automated outreach for qualified leads.
    Runs periodically to identify leads ready for outreach.
    """
    if not settings.AUTOMATED_OUTREACH_ENABLED:
        logger.debug("Automated outreach is disabled")
        return {"status": "disabled", "scheduled": 0}

    logger.info("Scheduling automated outreach for qualified leads")

    session = SessionLocal()
    try:
        # Find leads that are ready for outreach
        # - Stage is ENRICHED (qualified but not yet contacted)
        # - Have email addresses
        # - Haven't been contacted recently
        recent_cutoff = datetime.utcnow() - timedelta(days=7)

        ready_leads = session.query(Lead).filter(
            Lead.stage == LeadStage.ENRICHED.value,
            Lead.email.isnot(None),
            Lead.email != "",
        ).all()

        # Filter out leads that have recent outreach
        leads_to_contact = []
        for lead in ready_leads:
            existing_outreach = session.query(OutreachRequest).filter(
                OutreachRequest.contact_email == lead.email,
                OutreachRequest.created_at >= recent_cutoff
            ).first()

            if not existing_outreach:
                leads_to_contact.append(lead)

        # Limit the number of outreach emails per run to avoid overwhelming
        max_per_run = 5
        leads_to_contact = leads_to_contact[:max_per_run]

        scheduled_count = 0
        for lead in leads_to_contact:
            try:
                # Schedule the outreach task
                send_automated_outreach.delay(lead.id)
                scheduled_count += 1
                logger.info(f"Scheduled automated outreach for lead {lead.id}")

            except Exception as e:
                logger.error(f"Failed to schedule outreach for lead {lead.id}: {e}")

        logger.info(f"Scheduled {scheduled_count} automated outreach emails")
        return {
            "status": "completed",
            "leads_evaluated": len(ready_leads),
            "scheduled": scheduled_count,
        }

    except Exception as exc:
        logger.error(f"Failed to schedule automated outreach: {exc}")
        raise
    finally:
        session.close()


@celery_app.task
def cleanup_old_outreach_records():
    """
    Cleanup task to archive old completed outreach records.
    Runs weekly to prevent database bloat.
    """
    logger.info("Starting cleanup of old outreach records")

    session = SessionLocal()
    try:
        # Archive completed outreach older than 90 days
        cutoff_date = datetime.utcnow() - timedelta(days=90)

        # For now, just mark very old failed outreach as closed
        updated_count = session.query(OutreachRequest).filter(
            OutreachRequest.status == OutreachStatus.FAILED.value,
            OutreachRequest.created_at < cutoff_date
        ).update({"status": OutreachStatus.CLOSED.value})

        session.commit()

        logger.info(f"Cleaned up {updated_count} old outreach records")
        return {"updated_records": updated_count, "cutoff_date": cutoff_date.isoformat()}

    except Exception as exc:
        session.rollback()
        logger.error(f"Failed to cleanup old outreach records: {exc}")
        raise
    finally:
        session.close()


@celery_app.task
def get_outreach_statistics(days: int = 7) -> Dict[str, Any]:
    """
    Generate outreach statistics for monitoring and reporting.

    Args:
        days: Number of days to include in statistics

    Returns:
        Dict with outreach statistics
    """
    logger.info(f"Generating outreach statistics for last {days} days")

    session = SessionLocal()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Get outreach statistics
        outreach_requests = session.query(OutreachRequest).filter(
            OutreachRequest.created_at >= cutoff_date
        ).all()

        stats = {
            "period_days": days,
            "total_outreach_requests": len(outreach_requests),
            "sent": len([o for o in outreach_requests if o.status == OutreachStatus.SENT.value]),
            "delivered": len([o for o in outreach_requests if o.status == OutreachStatus.DELIVERED.value]),
            "replied": len([o for o in outreach_requests if o.status == OutreachStatus.REPLIED.value]),
            "failed": len([o for o in outreach_requests if o.status == OutreachStatus.FAILED.value]),
            "pending": len([o for o in outreach_requests if o.status in [
                OutreachStatus.DRAFT.value, OutreachStatus.QUEUED.value
            ]]),
            "reply_rate": 0,
            "delivery_rate": 0,
        }

        # Calculate rates
        sent_count = stats["sent"] + stats["delivered"] + stats["replied"]
        if sent_count > 0:
            stats["reply_rate"] = stats["replied"] / sent_count
            stats["delivery_rate"] = (stats["delivered"] + stats["replied"]) / sent_count

        return stats

    except Exception as exc:
        logger.error(f"Failed to generate outreach statistics: {exc}")
        raise
    finally:
        session.close()