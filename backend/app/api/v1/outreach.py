from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.schemas import OutreachRequest, OutreachResponse
from app.models.database import OutreachRequest as DBOutreachRequest
from app.models.enums import OutreachStatus
import uuid

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
    db: Session = Depends(get_db)
):
    """Send an outreach request email."""
    
    request = db.query(DBOutreachRequest).filter(DBOutreachRequest.id == outreach_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Outreach request not found")
    
    if request.status != OutreachStatus.DRAFT.value:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot send outreach with status: {request.status}"
        )
    
    # TODO: In Phase 3, this will integrate with AgentMail
    # For now, just update the status
    request.status = OutreachStatus.QUEUED.value
    
    db.commit()
    
    return {
        "message": "Outreach request queued for sending",
        "outreach_id": outreach_id,
        "status": request.status
    }

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
