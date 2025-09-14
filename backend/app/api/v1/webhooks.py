from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.database import OutreachRequest
from app.models.enums import OutreachStatus
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/agentmail")
async def agentmail_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """Webhook endpoint for AgentMail email events."""
    
    try:
        # Get the webhook payload
        payload = await request.json()
        logger.info(f"Received AgentMail webhook: {payload}")
        
        # TODO: In Phase 3, implement signature verification
        # verify_webhook_signature(request.headers, payload)
        
        event_type = payload.get("event_type")
        outreach_id = payload.get("metadata", {}).get("outreach_id")
        
        if not outreach_id:
            logger.warning("Webhook missing outreach_id in metadata")
            return {"status": "ignored", "reason": "missing outreach_id"}
        
        # Find the outreach request
        outreach = db.query(OutreachRequest).filter(
            OutreachRequest.id == outreach_id
        ).first()
        
        if not outreach:
            logger.warning(f"Outreach request not found: {outreach_id}")
            return {"status": "ignored", "reason": "outreach not found"}
        
        # Update status based on event type
        if event_type == "email.sent":
            outreach.status = OutreachStatus.SENT.value
            outreach.sent_at = db.func.now()
            outreach.message_id = payload.get("message_id")
            
        elif event_type == "email.delivered":
            outreach.status = OutreachStatus.DELIVERED.value
            
        elif event_type == "email.replied":
            outreach.status = OutreachStatus.REPLIED.value
            outreach.replied_at = db.func.now()
            
        elif event_type == "email.failed":
            # Keep existing status but log the failure
            logger.error(f"Email failed for outreach {outreach_id}: {payload}")
            
        else:
            logger.info(f"Unhandled event type: {event_type}")
            return {"status": "ignored", "reason": "unhandled event type"}
        
        db.commit()
        
        return {
            "status": "processed",
            "outreach_id": outreach_id,
            "event_type": event_type
        }
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")

@router.post("/browser-service")
async def browser_service_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """Webhook endpoint for Browser-Service task completion."""
    
    try:
        payload = await request.json()
        logger.info(f"Received Browser-Service webhook: {payload}")
        
        # TODO: In Phase 3, implement task result processing
        # This will update task status and store search results
        
        task_id = payload.get("task_id")
        if not task_id:
            return {"status": "ignored", "reason": "missing task_id"}
        
        return {
            "status": "processed",
            "task_id": task_id
        }
        
    except Exception as e:
        logger.error(f"Error processing browser service webhook: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")

@router.get("/health")
async def webhook_health():
    """Health check for webhook endpoints."""
    return {"status": "healthy", "service": "webhooks"}
