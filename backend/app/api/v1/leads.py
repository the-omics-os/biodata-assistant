from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models.schemas import LeadResponse, TaskResponse
from app.models.database import Lead, Task as DBTask
from app.models.enums import LeadStage, TaskType, TaskStatus
from app.core.tasks.github_prospecting_tasks import prospect_github_repos, run_daily_prospecting
from app.core.tasks.outreach_tasks import send_automated_outreach, schedule_automated_outreach
from app.config import settings
import uuid
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/prospect", response_model=TaskResponse)
async def trigger_github_prospecting(
    repos: Optional[str] = Query(None, description="Comma-separated list of repositories (owner/repo)"),
    max_issues: int = Query(25, ge=1, le=100, description="Maximum issues per repository"),
    user_email: Optional[str] = Query(None, description="User email for task tracking"),
    db: Session = Depends(get_db)
):
    """
    Trigger GitHub prospecting workflow as a background task.
    Returns task ID for monitoring progress.
    """
    # Parse repositories
    if repos:
        target_repos = [repo.strip() for repo in repos.split(",") if repo.strip()]
    else:
        target_repos = [repo.strip() for repo in settings.GITHUB_TARGET_REPOS.split(",") if repo.strip()]

    if not target_repos:
        raise HTTPException(status_code=400, detail="No target repositories specified")

    # Create task record
    task_id = str(uuid.uuid4())
    db_task = DBTask(
        id=task_id,
        type=TaskType.GITHUB_PROSPECTING.value,
        status=TaskStatus.PENDING.value,
        user_email=user_email or "api",
        input_data={
            "repos": target_repos,
            "max_issues_per_repo": max_issues,
            "triggered_by": "api",
        },
    )
    db.add(db_task)
    db.commit()

    # Start background task
    try:
        prospect_github_repos.delay(
            target_repos=target_repos,
            max_issues_per_repo=max_issues,
            user_email=user_email
        )

        logger.info(f"Started GitHub prospecting task {task_id} for repos: {target_repos}")

    except Exception as e:
        # Update task status to failed
        db_task.status = TaskStatus.FAILED.value
        db_task.error_message = f"Failed to start background task: {str(e)}"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to start prospecting task: {str(e)}")

    return TaskResponse(
        id=task_id,
        type=TaskType.GITHUB_PROSPECTING.value,
        status=TaskStatus.PENDING,
        user_email=user_email or "api",
        input_data=db_task.input_data,
        output_data=None,
        error_message=None,
        created_at=db_task.created_at,
        started_at=None,
        completed_at=None
    )


@router.post("/prospect/daily")
async def trigger_daily_prospecting(
    user_email: Optional[str] = Query(None, description="User email for task tracking"),
    db: Session = Depends(get_db)
):
    """
    Manually trigger the daily prospecting workflow.
    Uses the same settings as the scheduled daily task.
    """
    # Create task record
    task_id = str(uuid.uuid4())

    try:
        # Start the daily prospecting task
        run_daily_prospecting.delay()

        logger.info(f"Manually triggered daily prospecting task")

        return {
            "message": "Daily prospecting task started successfully",
            "status": "started",
            "scheduled_repos": settings.GITHUB_TARGET_REPOS.split(","),
            "max_issues_per_repo": settings.GITHUB_MAX_ISSUES_PER_REPO
        }

    except Exception as e:
        logger.error(f"Failed to start daily prospecting: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start daily prospecting: {str(e)}")


@router.get("", response_model=List[LeadResponse])
async def list_leads(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Number of records to return"),
    repo: Optional[str] = Query(None, description="Filter by repository"),
    stage: Optional[LeadStage] = Query(None, description="Filter by lead stage"),
    has_email: Optional[bool] = Query(None, description="Filter by presence of email"),
    min_score: Optional[float] = Query(None, ge=0, le=1, description="Minimum novice score"),
    created_since: Optional[datetime] = Query(None, description="Filter by creation date (ISO format)"),
    db: Session = Depends(get_db)
):
    """
    List GitHub leads with optional filtering and pagination.
    """
    query = db.query(Lead)

    # Apply filters
    if repo:
        query = query.filter(Lead.repo == repo)

    if stage:
        query = query.filter(Lead.stage == stage.value)

    if has_email is not None:
        if has_email:
            query = query.filter(Lead.email.isnot(None), Lead.email != "")
        else:
            query = query.filter(Lead.email.is_(None) | (Lead.email == ""))

    if min_score is not None:
        query = query.filter(Lead.novice_score >= min_score)

    if created_since:
        query = query.filter(Lead.created_at >= created_since)

    # Order by creation date, newest first
    query = query.order_by(Lead.created_at.desc())

    # Apply pagination
    leads = query.offset(skip).limit(limit).all()

    return [LeadResponse(
        id=lead.id,
        source=lead.source,
        repo=lead.repo,
        issue_number=lead.issue_number,
        issue_url=lead.issue_url,
        issue_title=lead.issue_title,
        issue_labels=lead.issue_labels,
        issue_created_at=lead.issue_created_at,
        user_login=lead.user_login,
        profile_url=lead.profile_url,
        email=lead.email,
        website=lead.website,
        signals=lead.signals,
        novice_score=lead.novice_score,
        stage=LeadStage(lead.stage),
        created_at=lead.created_at,
        updated_at=lead.updated_at
    ) for lead in leads]


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: str,
    db: Session = Depends(get_db)
):
    """
    Get a specific lead by ID.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    return LeadResponse(
        id=lead.id,
        source=lead.source,
        repo=lead.repo,
        issue_number=lead.issue_number,
        issue_url=lead.issue_url,
        issue_title=lead.issue_title,
        issue_labels=lead.issue_labels,
        issue_created_at=lead.issue_created_at,
        user_login=lead.user_login,
        profile_url=lead.profile_url,
        email=lead.email,
        website=lead.website,
        signals=lead.signals,
        novice_score=lead.novice_score,
        stage=LeadStage(lead.stage),
        created_at=lead.created_at,
        updated_at=lead.updated_at
    )


@router.put("/{lead_id}/stage")
async def update_lead_stage(
    lead_id: str,
    stage: LeadStage,
    db: Session = Depends(get_db)
):
    """
    Update the stage of a specific lead.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    old_stage = lead.stage
    lead.stage = stage.value
    lead.updated_at = datetime.utcnow()

    db.commit()

    return {
        "message": "Lead stage updated successfully",
        "lead_id": lead_id,
        "old_stage": old_stage,
        "new_stage": stage.value,
        "updated_at": lead.updated_at
    }


@router.post("/{lead_id}/outreach")
async def send_lead_outreach(
    lead_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Send outreach email to a specific lead.
    Creates a background task to handle the email sending.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if not lead.email:
        raise HTTPException(status_code=400, detail="Lead has no email address")

    # Check if outreach was sent recently
    recent_cutoff = datetime.utcnow() - timedelta(days=7)
    from app.models.database import OutreachRequest

    existing_outreach = db.query(OutreachRequest).filter(
        OutreachRequest.contact_email == lead.email,
        OutreachRequest.created_at >= recent_cutoff
    ).first()

    if existing_outreach:
        raise HTTPException(
            status_code=400,
            detail="Outreach was already sent to this lead recently"
        )

    try:
        # Schedule outreach as background task
        send_automated_outreach.delay(lead_id)

        logger.info(f"Scheduled outreach for lead {lead_id}")

        return {
            "message": "Outreach email scheduled successfully",
            "lead_id": lead_id,
            "contact_email": lead.email,
            "status": "scheduled"
        }

    except Exception as e:
        logger.error(f"Failed to schedule outreach for lead {lead_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to schedule outreach: {str(e)}")


@router.post("/outreach/bulk")
async def send_bulk_outreach(
    lead_ids: List[str],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Send outreach emails to multiple leads.
    Each outreach is handled as a separate background task.
    """
    if len(lead_ids) > 50:  # Reasonable limit
        raise HTTPException(status_code=400, detail="Cannot send outreach to more than 50 leads at once")

    # Validate all leads exist and have email addresses
    leads = db.query(Lead).filter(Lead.id.in_(lead_ids)).all()

    if len(leads) != len(lead_ids):
        raise HTTPException(status_code=400, detail="Some leads not found")

    leads_without_email = [lead for lead in leads if not lead.email]
    if leads_without_email:
        raise HTTPException(
            status_code=400,
            detail=f"Some leads have no email address: {[lead.id for lead in leads_without_email]}"
        )

    # Check for recent outreach
    recent_cutoff = datetime.utcnow() - timedelta(days=7)
    from app.models.database import OutreachRequest

    leads_with_recent_outreach = []
    for lead in leads:
        existing = db.query(OutreachRequest).filter(
            OutreachRequest.contact_email == lead.email,
            OutreachRequest.created_at >= recent_cutoff
        ).first()
        if existing:
            leads_with_recent_outreach.append(lead.id)

    if leads_with_recent_outreach:
        raise HTTPException(
            status_code=400,
            detail=f"Recent outreach exists for leads: {leads_with_recent_outreach}"
        )

    # Schedule outreach for all leads
    scheduled_count = 0
    errors = []

    for lead in leads:
        try:
            send_automated_outreach.delay(lead.id)
            scheduled_count += 1
            logger.info(f"Scheduled bulk outreach for lead {lead.id}")
        except Exception as e:
            errors.append({"lead_id": lead.id, "error": str(e)})
            logger.error(f"Failed to schedule outreach for lead {lead.id}: {e}")

    return {
        "message": f"Bulk outreach scheduled for {scheduled_count} leads",
        "scheduled": scheduled_count,
        "total_requested": len(lead_ids),
        "errors": errors
    }


@router.post("/outreach/schedule-automated")
async def trigger_automated_outreach_scheduling():
    """
    Manually trigger the automated outreach scheduling task.
    This identifies qualified leads and schedules outreach for them.
    """
    try:
        schedule_automated_outreach.delay()

        logger.info("Triggered automated outreach scheduling")

        return {
            "message": "Automated outreach scheduling triggered successfully",
            "status": "started",
            "note": "Leads will be evaluated and outreach scheduled based on qualification criteria"
        }

    except Exception as e:
        logger.error(f"Failed to trigger automated outreach scheduling: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger scheduling: {str(e)}")


@router.get("/stats/summary")
async def get_leads_summary(
    days: int = Query(7, ge=1, le=90, description="Number of days for statistics"),
    db: Session = Depends(get_db)
):
    """
    Get summary statistics for GitHub leads.
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Get total counts
    total_leads = db.query(Lead).count()
    recent_leads = db.query(Lead).filter(Lead.created_at >= cutoff_date).count()

    # Get leads by stage
    stages_query = db.query(Lead.stage, db.func.count(Lead.id)).group_by(Lead.stage).all()
    leads_by_stage = {stage: count for stage, count in stages_query}

    # Get leads by repository
    repos_query = db.query(Lead.repo, db.func.count(Lead.id)).group_by(Lead.repo).all()
    leads_by_repo = {repo: count for repo, count in repos_query}

    # Get leads with email
    leads_with_email = db.query(Lead).filter(Lead.email.isnot(None), Lead.email != "").count()

    # Average novice score
    avg_score_result = db.query(db.func.avg(Lead.novice_score)).scalar()
    avg_novice_score = float(avg_score_result) if avg_score_result else 0.0

    return {
        "period_days": days,
        "total_leads": total_leads,
        "recent_leads": recent_leads,
        "leads_with_email": leads_with_email,
        "email_percentage": (leads_with_email / total_leads * 100) if total_leads > 0 else 0,
        "average_novice_score": round(avg_novice_score, 2),
        "leads_by_stage": leads_by_stage,
        "leads_by_repo": leads_by_repo,
    }


@router.get("/stats/repositories")
async def get_repository_stats(
    db: Session = Depends(get_db)
):
    """
    Get detailed statistics by repository.
    """
    # Get comprehensive stats by repository
    repos = db.query(Lead.repo).distinct().all()
    repo_stats = {}

    for (repo,) in repos:
        repo_leads = db.query(Lead).filter(Lead.repo == repo).all()

        stages = {}
        for lead in repo_leads:
            stage = lead.stage
            stages[stage] = stages.get(stage, 0) + 1

        email_count = len([lead for lead in repo_leads if lead.email])
        total_score = sum(lead.novice_score for lead in repo_leads)
        avg_score = total_score / len(repo_leads) if repo_leads else 0

        repo_stats[repo] = {
            "total_leads": len(repo_leads),
            "leads_with_email": email_count,
            "email_percentage": (email_count / len(repo_leads) * 100) if repo_leads else 0,
            "average_novice_score": round(avg_score, 2),
            "leads_by_stage": stages,
        }

    return repo_stats