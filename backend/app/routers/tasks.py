"""
Task routes for managing AI agent tasks.
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Task
from app.routers.chat import get_current_user

router = APIRouter()


@router.get("/")
async def get_tasks(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get all tasks for the current user.
    """
    user = get_current_user(authorization, db)
    
    query = db.query(Task).filter(Task.user_id == user.id)
    
    if status_filter:
        query = query.filter(Task.status == status_filter)
    
    tasks = query.order_by(Task.created_at.desc()).all()
    
    return [
        {
            "id": task.id,
            "task_type": task.task_type,
            "status": task.status,
            "description": task.description,
            "input_data": task.input_data,
            "current_state": task.current_state,
            "result": task.result,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None
        }
        for task in tasks
    ]


@router.get("/{task_id}")
async def get_task(
    task_id: int,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Get a specific task by ID.
    """
    user = get_current_user(authorization, db)
    
    task = db.query(Task).filter(
        Task.id == task_id,
        Task.user_id == user.id
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {
        "id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "description": task.description,
        "input_data": task.input_data,
        "current_state": task.current_state,
        "result": task.result,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None
    }

