from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from app.core.database import get_db
from app.models.schemas import OutreachRequest, OutreachResponse
from app.models.database import OutreachRequest as DBOutreachRequest
from app.models.enums import OutreachStatus
from app.core.tasks.outreach_tasks import send_single_outreach, get_outreach_statistics
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("", response_model=List[OutreachResponse])
async def list_outreach_requests(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[OutreachStatus] = None,
    requester_email: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all outreach requests with optional filtering."""
    
    query = db.query(DBOutreachRequest)
    
    if status:
        query = query.filter(DBOutreachRequest.status == status.value)
        
    if requester_email:
        query = query.filter(DBOutreachRequest.requester_email == requester_email)
    
    # Order by creation date, newest first
    query = query.order_by(DBOutreachRequest.created_at.desc())
    
    requests = query.offset(skip).limit(limit).all()
    
    return [OutreachResponse(
        id=req.id,
        dataset_id=req.dataset_id,
        requester_email=req.requester_email,
        requester_name=req.requester_name,
        contact_email=req.contact_email,
        contact_name=req.contact_name,
        status=OutreachStatus(req.status),
        email_subject=req.email_subject,
        email_body=req.email_body,
        created_at=req.created_at,
        sent_at=req.sent_at
    ) for req in requests]

@router.get("/{outreach_id}", response_model=OutreachResponse)
async def get_outreach_request(
    outreach_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific outreach request by ID."""
    
    request = db.query(DBOutreachRequest).filter(DBOutreachRequest.id == outreach_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Outreach request not found")
    
    return OutreachResponse(
        id=request.id,
        dataset_id=request.dataset_id,
        requester_email=request.requester_email,
        requester_name=request.requester_name,
        contact_email=request.contact_email,
        contact_name=request.contact_name,
        status=OutreachStatus(request.status),
        email_subject=request.email_subject,
        email_body=request.email_body,
        created_at=request.created_at,
        sent_at=request.sent_at
    )

@router.post("", response_model=OutreachResponse)
async def create_outreach_request(
    outreach: OutreachRequest,
    db: Session = Depends(get_db)
):
    """Create a new outreach request."""
    
    outreach_id = str(uuid.uuid4())
    db_outreach = DBOutreachRequest(
        id=outreach_id,
        dataset_id=outreach.dataset_id,
        requester_email=outreach.requester_email,
        requester_name=outreach.requester_name,
        contact_email=outreach.contact_email,
        contact_name=outreach.contact_name,
        status=OutreachStatus.DRAFT.value,
        email_subject=outreach.email_subject,
        email_body=outreach.email_body,
        approval_required=outreach.approval_required
    )
    
    db.add(db_outreach)
    db.commit()
    db.refresh(db_outreach)
    
    return OutreachResponse(
        id=db_outreach.id,
        dataset_id=db_outreach.dataset_id,
        requester_email=db_outreach.requester_email,
        requester_name=db_outreach.requester_name,
        contact_email=db_outreach.contact_email,
        contact_name=db_outreach.contact_name,
        status=OutreachStatus(db_outreach.status),
        email_subject=db_outreach.email_subject,
        email_body=db_outreach.email_body,
        created_at=db_outreach.created_at,
        sent_at=db_outreach.sent_at
    )

@router.post("/{outreach_id}/send")
async def send_outreach_request(
    outreach_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Send an outreach request email via background task."""

    request = db.query(DBOutreachRequest).filter(DBOutreachRequest.id == outreach_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Outreach request not found")

    if request.status not in [OutreachStatus.DRAFT.value, OutreachStatus.FAILED.value]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot send outreach with status: {request.status}"
        )

    # Update status to queued
    request.status = OutreachStatus.QUEUED.value
    db.commit()

    try:
        # Schedule background task to send the email
        send_single_outreach.delay(outreach_id)

        logger.info(f"Scheduled outreach sending for {outreach_id}")

        return {
            "message": "Outreach request queued for sending",
            "outreach_id": outreach_id,
            "status": request.status
        }

    except Exception as e:
        # Revert status if task scheduling failed
        request.status = OutreachStatus.DRAFT.value
        db.commit()

        logger.error(f"Failed to schedule outreach {outreach_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to schedule outreach: {str(e)}")

@router.put("/{outreach_id}/status")
async def update_outreach_status(
    outreach_id: str,
    status: OutreachStatus,
    db: Session = Depends(get_db)
):
    """Update the status of an outreach request (for webhook updates)."""
    
    request = db.query(DBOutreachRequest).filter(DBOutreachRequest.id == outreach_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Outreach request not found")
    
    request.status = status.value
    
    # Set timestamps based on status
    if status == OutreachStatus.SENT:
        request.sent_at = db.func.now()
    elif status == OutreachStatus.REPLIED:
        request.replied_at = db.func.now()
    
    db.commit()
    
    return {
        "message": "Outreach status updated successfully",
        "outreach_id": outreach_id,
        "status": status.value
    }


@router.post("/{outreach_id}/approve")
async def approve_outreach_request(
    outreach_id: str,
    approved_by: str = Query(..., description="Email of person approving the outreach"),
    db: Session = Depends(get_db)
):
    """Approve an outreach request that requires approval."""

    request = db.query(DBOutreachRequest).filter(DBOutreachRequest.id == outreach_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Outreach request not found")

    if not request.approval_required:
        raise HTTPException(status_code=400, detail="This outreach request does not require approval")

    if request.approved_at:
        raise HTTPException(status_code=400, detail="Outreach request already approved")

    # Approve the request
    request.approved_at = datetime.utcnow()
    request.approved_by = approved_by

    # If it's in draft status, move it to queued so it can be processed
    if request.status == OutreachStatus.DRAFT.value:
        request.status = OutreachStatus.QUEUED.value

    db.commit()

    logger.info(f"Outreach {outreach_id} approved by {approved_by}")

    return {
        "message": "Outreach request approved successfully",
        "outreach_id": outreach_id,
        "approved_by": approved_by,
        "approved_at": request.approved_at,
        "status": request.status
    }


@router.post("/bulk-send")
async def send_bulk_outreach(
    outreach_ids: List[str],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Send multiple outreach requests as background tasks."""

    if len(outreach_ids) > 50:  # Reasonable limit
        raise HTTPException(status_code=400, detail="Cannot send more than 50 outreach requests at once")

    # Validate all outreach requests exist and are in sendable status
    requests = db.query(DBOutreachRequest).filter(DBOutreachRequest.id.in_(outreach_ids)).all()

    if len(requests) != len(outreach_ids):
        raise HTTPException(status_code=400, detail="Some outreach requests not found")

    # Check status of all requests
    invalid_requests = []
    for req in requests:
        if req.status not in [OutreachStatus.DRAFT.value, OutreachStatus.FAILED.value]:
            invalid_requests.append(req.id)

    if invalid_requests:
        raise HTTPException(
            status_code=400,
            detail=f"Some requests cannot be sent due to status: {invalid_requests}"
        )

    # Check approval requirements
    unapproved_requests = []
    for req in requests:
        if req.approval_required and not req.approved_at:
            unapproved_requests.append(req.id)

    if unapproved_requests:
        raise HTTPException(
            status_code=400,
            detail=f"Some requests require approval: {unapproved_requests}"
        )

    # Update all to queued status and schedule tasks
    scheduled_count = 0
    errors = []

    for req in requests:
        try:
            req.status = OutreachStatus.QUEUED.value
            send_single_outreach.delay(req.id)
            scheduled_count += 1
            logger.info(f"Scheduled bulk outreach for {req.id}")
        except Exception as e:
            errors.append({"outreach_id": req.id, "error": str(e)})
            logger.error(f"Failed to schedule outreach {req.id}: {e}")

    db.commit()

    return {
        "message": f"Bulk outreach scheduled for {scheduled_count} requests",
        "scheduled": scheduled_count,
        "total_requested": len(outreach_ids),
        "errors": errors
    }


@router.get("/stats/summary")
async def get_outreach_summary(
    days: int = Query(7, ge=1, le=90, description="Number of days for statistics"),
    db: Session = Depends(get_db)
):
    """Get outreach statistics summary."""

    try:
        # Use the background task to get statistics
        stats = get_outreach_statistics(days=days)
        return stats

    except Exception as e:
        logger.error(f"Failed to get outreach statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")


@router.get("/queue/status")
async def get_queue_status(db: Session = Depends(get_db)):
    """Get current status of the outreach queue."""

    # Count requests by status
    status_counts = {}
    for status in OutreachStatus:
        count = db.query(DBOutreachRequest).filter(DBOutreachRequest.status == status.value).count()
        status_counts[status.value] = count

    # Get recent activity (last 24 hours)
    recent_cutoff = datetime.utcnow() - timedelta(hours=24)
    recent_sent = db.query(DBOutreachRequest).filter(
        DBOutreachRequest.sent_at >= recent_cutoff
    ).count()

    recent_replies = db.query(DBOutreachRequest).filter(
        DBOutreachRequest.replied_at >= recent_cutoff
    ).count()

    # Get oldest queued request
    oldest_queued = db.query(DBOutreachRequest).filter(
        DBOutreachRequest.status == OutreachStatus.QUEUED.value
    ).order_by(DBOutreachRequest.created_at.asc()).first()

    return {
        "status_counts": status_counts,
        "recent_activity": {
            "sent_last_24h": recent_sent,
            "replies_last_24h": recent_replies,
        },
        "queue_info": {
            "queued_count": status_counts.get(OutreachStatus.QUEUED.value, 0),
            "oldest_queued_at": oldest_queued.created_at if oldest_queued else None,
        }
    }
