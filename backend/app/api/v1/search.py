from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.database import get_db, SessionLocal
from app.models.schemas import SearchRequest, SearchResponse, TaskResponse
from app.core.agent_orchestrator import AgentOrchestrator
from app.models.database import Task
from app.models.enums import TaskType, TaskStatus
from datetime import datetime
import uuid
import logging

router = APIRouter()
orchestrator = AgentOrchestrator()

@router.post("", response_model=SearchResponse)
async def initiate_search(
    search_request: SearchRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Initiate a new dataset search task."""
    
    # Create a new task record
    task_id = str(uuid.uuid4())
    task = Task(
        id=task_id,
        type=TaskType.SEARCH.value,
        status=TaskStatus.PENDING.value,
        user_email=None,  # Will be populated when user auth is implemented
        input_data=search_request.dict(),
        started_at=datetime.utcnow()
    )
    
    db.add(task)
    db.commit()
    db.refresh(task)

    # Kick off agentic workflow in background
    background_tasks.add_task(_run_agentic_search, task_id, search_request.dict())

    return SearchResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message="Search task initiated successfully"
    )

async def _run_agentic_search(task_id: str, req_data: dict) -> None:
    """Background task to execute the multi-agent workflow and persist results."""
    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = TaskStatus.RUNNING.value
            task.started_at = datetime.utcnow()
            db.commit()

        request = SearchRequest(**req_data)
        user_email = task.user_email if task and task.user_email else ""
        result = await orchestrator.execute_workflow(request, user_email=user_email)

        # Persist results
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = TaskStatus.COMPLETED.value
            task.output_data = result
            task.completed_at = datetime.utcnow()
            db.commit()
    except Exception as e:
        logger.error(f"Agent workflow failed for task {task_id}: {e}")
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = TaskStatus.FAILED.value
                task.error_message = str(e)
                task.completed_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
    finally:
        try:
            db.close()
        except Exception:
            pass

@router.get("/{task_id}", response_model=TaskResponse)
async def get_search_status(
    task_id: str,
    db: Session = Depends(get_db)
):
    """Get the status of a search task."""
    
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskResponse(
        id=task.id,
        type=task.type,
        status=TaskStatus(task.status),
        user_email=task.user_email,
        input_data=task.input_data,
        output_data=task.output_data,
        error_message=task.error_message,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at
    )

@router.get("/{task_id}/results")
async def get_search_results(
    task_id: str,
    db: Session = Depends(get_db)
):
    """Get the results of a completed search task."""
    
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status != TaskStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400, 
            detail=f"Task is not completed. Current status: {task.status}"
        )
    
    return {
        "task_id": task_id,
        "status": task.status,
        "results": task.output_data or [],
        "completed_at": task.completed_at
    }
