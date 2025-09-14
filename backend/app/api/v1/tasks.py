from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.schemas import TaskResponse
from app.models.database import Task
from app.models.enums import TaskType, TaskStatus

router = APIRouter()

@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    task_type: Optional[TaskType] = None,
    status: Optional[TaskStatus] = None,
    user_email: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all tasks with optional filtering."""
    
    query = db.query(Task)
    
    if task_type:
        query = query.filter(Task.type == task_type.value)
    
    if status:
        query = query.filter(Task.status == status.value)
        
    if user_email:
        query = query.filter(Task.user_email == user_email)
    
    # Order by creation date, newest first
    query = query.order_by(Task.created_at.desc())
    
    tasks = query.offset(skip).limit(limit).all()
    
    return [TaskResponse(
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
    ) for task in tasks]

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific task by ID."""
    
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

@router.delete("/{task_id}")
async def cancel_task(
    task_id: str,
    db: Session = Depends(get_db)
):
    """Cancel a pending or running task."""
    
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status not in [TaskStatus.PENDING.value, TaskStatus.RUNNING.value]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel task with status: {task.status}"
        )
    
    # Mark as failed with cancellation message
    task.status = TaskStatus.FAILED.value
    task.error_message = "Task cancelled by user"
    task.completed_at = db.func.now()
    
    db.commit()
    
    return {"message": "Task cancelled successfully"}

@router.get("/{task_id}/logs")
async def get_task_logs(
    task_id: str,
    db: Session = Depends(get_db)
):
    """Get logs for a specific task (placeholder for future implementation)."""
    
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # TODO: Implement actual logging system in Phase 2
    return {
        "task_id": task_id,
        "logs": [
            {
                "timestamp": task.created_at,
                "level": "INFO",
                "message": f"Task {task.type} created"
            }
        ]
    }
