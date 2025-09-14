from __future__ import annotations

import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from celery import current_task
from app.core.celery_app import celery_app
from app.config import settings
from app.core.agents.github_leads_agent import prospect_github_issues
from app.core.utils.provenance import log_provenance
from app.models.database import Task as DBTask, Lead
from app.models.enums import TaskType, TaskStatus, LeadStage
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def run_daily_prospecting(self):
    """
    Daily GitHub prospecting task that runs automatically via Celery Beat.
    Extracts configuration from settings and runs the full prospecting workflow.
    """
    logger.info("Starting daily GitHub prospecting task")

    # Create task record in database
    task_id = str(current_task.request.id) if current_task else None
    db_task = None

    session = SessionLocal()
    try:
        if task_id:
            db_task = DBTask(
                id=task_id,
                type=TaskType.GITHUB_PROSPECTING.value,
                status=TaskStatus.RUNNING.value,
                user_email="system",
                input_data={
                    "repos": settings.GITHUB_TARGET_REPOS.split(","),
                    "max_issues_per_repo": settings.GITHUB_MAX_ISSUES_PER_REPO,
                    "scheduled": True,
                },
                started_at=datetime.utcnow(),
            )
            session.add(db_task)
            session.commit()

        # Parse target repositories from settings
        target_repos = [repo.strip() for repo in settings.GITHUB_TARGET_REPOS.split(",") if repo.strip()]

        # Run the prospecting workflow
        result = asyncio.run(_run_prospecting_workflow(
            target_repos=target_repos,
            max_issues_per_repo=settings.GITHUB_MAX_ISSUES_PER_REPO,
            task_id=task_id,
        ))

        # Update task record with results
        if db_task:
            db_task.status = TaskStatus.COMPLETED.value
            db_task.output_data = result
            db_task.completed_at = datetime.utcnow()
            session.commit()

        logger.info(f"Daily prospecting completed successfully: {result['total_leads']} leads found")
        return result

    except Exception as exc:
        logger.error(f"Daily prospecting task failed: {exc}")

        # Update task record with error
        if db_task:
            db_task.status = TaskStatus.FAILED.value
            db_task.error_message = str(exc)
            db_task.completed_at = datetime.utcnow()
            session.commit()

        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            retry_delay = 60 * (2 ** self.request.retries)  # 60s, 2m, 4m
            logger.info(f"Retrying daily prospecting in {retry_delay} seconds (attempt {self.request.retries + 1})")
            raise self.retry(countdown=retry_delay, exc=exc)

        raise
    finally:
        session.close()


@celery_app.task(bind=True, max_retries=2)
def prospect_github_repos(self, target_repos: List[str], max_issues_per_repo: int = 25, user_email: Optional[str] = None):
    """
    Background task to prospect specific GitHub repositories.
    Can be triggered via API endpoints.

    Args:
        target_repos: List of repositories in "owner/repo" format
        max_issues_per_repo: Maximum issues to fetch per repository
        user_email: Email of user who triggered the task (optional)
    """
    logger.info(f"Starting GitHub prospecting for repos: {target_repos}")

    # Create task record in database
    task_id = str(current_task.request.id) if current_task else None
    db_task = None

    session = SessionLocal()
    try:
        if task_id:
            db_task = DBTask(
                id=task_id,
                type=TaskType.GITHUB_PROSPECTING.value,
                status=TaskStatus.RUNNING.value,
                user_email=user_email or "api",
                input_data={
                    "repos": target_repos,
                    "max_issues_per_repo": max_issues_per_repo,
                    "scheduled": False,
                },
                started_at=datetime.utcnow(),
            )
            session.add(db_task)
            session.commit()

        # Run the prospecting workflow
        result = asyncio.run(_run_prospecting_workflow(
            target_repos=target_repos,
            max_issues_per_repo=max_issues_per_repo,
            task_id=task_id,
        ))

        # Update task record with results
        if db_task:
            db_task.status = TaskStatus.COMPLETED.value
            db_task.output_data = result
            db_task.completed_at = datetime.utcnow()
            session.commit()

        logger.info(f"GitHub prospecting completed: {result['total_leads']} leads found")
        return result

    except Exception as exc:
        logger.error(f"GitHub prospecting task failed: {exc}")

        # Update task record with error
        if db_task:
            db_task.status = TaskStatus.FAILED.value
            db_task.error_message = str(exc)
            db_task.completed_at = datetime.utcnow()
            session.commit()

        # Retry with backoff
        if self.request.retries < self.max_retries:
            retry_delay = 30 * (2 ** self.request.retries)  # 30s, 60s
            logger.info(f"Retrying GitHub prospecting in {retry_delay} seconds")
            raise self.retry(countdown=retry_delay, exc=exc)

        raise
    finally:
        session.close()


@celery_app.task(bind=True)
def process_single_repository(self, repo: str, max_issues: int = 25):
    """
    Process a single GitHub repository for leads.
    Used for parallel processing of multiple repositories.

    Args:
        repo: Repository in "owner/repo" format
        max_issues: Maximum issues to fetch from this repository
    """
    logger.info(f"Processing single repository: {repo}")

    try:
        result = asyncio.run(_process_repository(repo, max_issues))
        logger.info(f"Repository {repo} processed: {len(result)} leads found")
        return {
            "repo": repo,
            "leads_found": len(result),
            "leads": result,
            "success": True,
        }

    except Exception as exc:
        logger.error(f"Failed to process repository {repo}: {exc}")
        return {
            "repo": repo,
            "leads_found": 0,
            "leads": [],
            "success": False,
            "error": str(exc),
        }


async def _run_prospecting_workflow(
    target_repos: List[str],
    max_issues_per_repo: int,
    task_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Core prospecting workflow that leverages the existing github_leads_agent.

    Returns:
        Dict with prospecting results and statistics
    """
    start_time = datetime.utcnow()

    # Log workflow start
    await log_provenance(
        actor="github_prospecting_task",
        action="prospecting_workflow_started",
        resource_type="task",
        resource_id=task_id or "unknown",
        details={
            "target_repos": target_repos,
            "max_issues_per_repo": max_issues_per_repo,
        },
    )

    try:
        # Use the existing prospect_github_issues function
        leads = await prospect_github_issues(
            target_repos=target_repos,
            max_issues_per_repo=max_issues_per_repo,
            require_email=True,  # Only include leads with contact info
            persist_to_db=True,  # Save to database
            profile_enrichment="browser",  # Use browser-based enrichment
        )

        # Calculate statistics
        leads_by_repo = {}
        total_leads = len(leads)

        for lead in leads:
            repo = lead.get("repo", "unknown")
            leads_by_repo[repo] = leads_by_repo.get(repo, 0) + 1

        # Calculate processing time
        end_time = datetime.utcnow()
        processing_time = (end_time - start_time).total_seconds()

        result = {
            "success": True,
            "total_leads": total_leads,
            "leads_by_repo": leads_by_repo,
            "target_repos": target_repos,
            "processing_time_seconds": processing_time,
            "completed_at": end_time.isoformat(),
        }

        # Log successful completion
        await log_provenance(
            actor="github_prospecting_task",
            action="prospecting_workflow_completed",
            resource_type="task",
            resource_id=task_id or "unknown",
            details=result,
        )

        return result

    except Exception as exc:
        # Log failure
        await log_provenance(
            actor="github_prospecting_task",
            action="prospecting_workflow_failed",
            resource_type="task",
            resource_id=task_id or "unknown",
            details={
                "error": str(exc),
                "target_repos": target_repos,
            },
        )
        raise


async def _process_repository(repo: str, max_issues: int) -> List[Dict[str, Any]]:
    """
    Process a single repository for leads.
    Helper function for parallel processing.
    """
    try:
        leads = await prospect_github_issues(
            target_repos=[repo],
            max_issues_per_repo=max_issues,
            require_email=True,
            persist_to_db=True,
            profile_enrichment="browser",
        )
        return leads

    except Exception as exc:
        logger.error(f"Failed to process repository {repo}: {exc}")
        return []


@celery_app.task
def cleanup_old_prospecting_tasks():
    """
    Cleanup task to remove old completed prospecting tasks from the database.
    Runs weekly to prevent database bloat.
    """
    logger.info("Starting cleanup of old prospecting tasks")

    session = SessionLocal()
    try:
        # Delete completed tasks older than 30 days
        cutoff_date = datetime.utcnow() - timedelta(days=30)

        deleted_count = session.query(DBTask).filter(
            DBTask.type == TaskType.GITHUB_PROSPECTING.value,
            DBTask.status.in_([TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]),
            DBTask.completed_at < cutoff_date
        ).delete()

        session.commit()

        logger.info(f"Cleaned up {deleted_count} old prospecting tasks")
        return {"deleted_tasks": deleted_count, "cutoff_date": cutoff_date.isoformat()}

    except Exception as exc:
        session.rollback()
        logger.error(f"Failed to cleanup old tasks: {exc}")
        raise
    finally:
        session.close()


@celery_app.task
def get_prospecting_statistics(days: int = 7) -> Dict[str, Any]:
    """
    Generate prospecting statistics for the last N days.
    Used for monitoring and reporting.

    Args:
        days: Number of days to include in statistics
    """
    logger.info(f"Generating prospecting statistics for last {days} days")

    session = SessionLocal()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Get task statistics
        tasks = session.query(DBTask).filter(
            DBTask.type == TaskType.GITHUB_PROSPECTING.value,
            DBTask.created_at >= cutoff_date
        ).all()

        # Get lead statistics
        leads = session.query(Lead).filter(
            Lead.created_at >= cutoff_date
        ).all()

        stats = {
            "period_days": days,
            "total_prospecting_tasks": len(tasks),
            "successful_tasks": len([t for t in tasks if t.status == TaskStatus.COMPLETED.value]),
            "failed_tasks": len([t for t in tasks if t.status == TaskStatus.FAILED.value]),
            "total_leads_generated": len(leads),
            "leads_by_repo": {},
            "leads_by_stage": {},
            "average_processing_time": 0,
        }

        # Calculate leads by repository
        for lead in leads:
            repo = lead.repo
            stats["leads_by_repo"][repo] = stats["leads_by_repo"].get(repo, 0) + 1

        # Calculate leads by stage
        for lead in leads:
            stage = lead.stage
            stats["leads_by_stage"][stage] = stats["leads_by_stage"].get(stage, 0) + 1

        # Calculate average processing time for completed tasks
        completed_tasks = [t for t in tasks if t.status == TaskStatus.COMPLETED.value and t.started_at and t.completed_at]
        if completed_tasks:
            total_time = sum((t.completed_at - t.started_at).total_seconds() for t in completed_tasks)
            stats["average_processing_time"] = total_time / len(completed_tasks)

        return stats

    except Exception as exc:
        logger.error(f"Failed to generate statistics: {exc}")
        raise
    finally:
        session.close()