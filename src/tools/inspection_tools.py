"""Inspection task tools — Pydantic-validated function implementations.

These are the actual tool functions that the Agent calls via LangGraph
function calling. Each function:
  1. Validates input with Pydantic
  2. Executes the operation
  3. Returns a structured InspectionTaskResult
"""
from __future__ import annotations

from pathlib import Path

from src.tools.schemas import (
    CREATE_TASK_SCHEMA,
    CLOSE_TASK_SCHEMA,
    LIST_TASKS_SCHEMA,
    InspectionTaskCreate,
    InspectionTaskResult,
    TaskStatusUpdate,
)
from src.tools.task_store import (
    close_task as store_close_task,
)
from src.tools.task_store import (
    create_task as store_create_task,
)
from src.tools.task_store import (
    get_store_stats,
    list_open_tasks as store_list_open,
)
from src.tools.task_store import (
    list_tasks as store_list_tasks,
)

_DEFAULT_STORE = Path("data/runtime/tasks.json")


# ============================================================
# Tool: create_inspection_task
# ============================================================

def create_inspection_task(
    task_type: str,
    priority: str,
    target_id: str,
    title: str,
    description: str,
    sop_reference: str = "",
    assignee: str = "",
) -> dict:
    """Create a new inspection task.

    Args correspond to CREATE_TASK_SCHEMA parameters.

    Returns:
        Dict with success, task_id, message, and task fields.
    """
    try:
        task_input = InspectionTaskCreate(
            task_type=task_type,
            priority=priority,
            target_id=target_id,
            title=title,
            description=description,
            sop_reference=sop_reference,
            assignee=assignee,
        )
    except Exception as e:
        return InspectionTaskResult(
            success=False,
            message=f"Validation error: {e}",
        ).model_dump()

    task = store_create_task(task_input)
    return InspectionTaskResult(
        success=True,
        task_id=task.task_id,
        message=f"Task {task.task_id} created: {task.title}",
        task=task,
    ).model_dump()


# ============================================================
# Tool: list_inspection_tasks
# ============================================================

def list_inspection_tasks(
    status: str | None = None,
    task_type: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
    limit: int = 20,
) -> dict:
    """List inspection tasks with optional filters.

    Returns:
        Dict with success, message, and tasks list.
    """
    if limit < 1 or limit > 100:
        limit = 20

    tasks = store_list_tasks(
        status=status,
        task_type=task_type,
        priority=priority,
        assignee=assignee,
        limit=limit,
    )

    return InspectionTaskResult(
        success=True,
        message=f"Found {len(tasks)} task(s)",
    ).model_dump() | {
        "tasks": [t.to_openai_schema() for t in tasks],
        "count": len(tasks),
    }


# ============================================================
# Tool: list_open_tasks
# ============================================================

def list_open_tasks() -> dict:
    """List all open (pending + in_progress) tasks, P0 first.

    Returns:
        Dict with success, message, and tasks list.
    """
    tasks = store_list_open()
    return InspectionTaskResult(
        success=True,
        message=f"Found {len(tasks)} open task(s)",
    ).model_dump() | {
        "tasks": [t.to_openai_schema() for t in tasks],
        "count": len(tasks),
    }


# ============================================================
# Tool: close_inspection_task
# ============================================================

def close_inspection_task(
    task_id: str,
    status: str = "resolved",
    resolution_note: str = "",
) -> dict:
    """Close or resolve an inspection task.

    Args:
        task_id: Task ID to close (e.g. YJ-20260527-0001).
        status: Target status — resolved, closed, or ignored.
        resolution_note: Explanation of resolution.

    Returns:
        Dict with success, task_id, message, and updated task.
    """
    valid_statuses = {"resolved", "closed", "ignored"}
    if status not in valid_statuses:
        return InspectionTaskResult(
            success=False,
            task_id=task_id,
            message=f"Invalid status '{status}'. Must be one of {valid_statuses}",
        ).model_dump()

    update = TaskStatusUpdate(
        task_id=task_id,
        status=status,
        resolution_note=resolution_note,
    )

    from src.tools.task_store import update_task

    task = update_task(update)
    if task is None:
        return InspectionTaskResult(
            success=False,
            task_id=task_id,
            message=f"Task {task_id} not found",
        ).model_dump()

    return InspectionTaskResult(
        success=True,
        task_id=task_id,
        message=f"Task {task_id} updated to {status}",
        task=task,
    ).model_dump()


# ============================================================
# Tool: get_task_stats
# ============================================================

def get_task_stats() -> dict:
    """Return aggregate task statistics for dashboard display.

    Returns:
        Dict with total, by_status, by_type, by_priority counts.
    """
    stats = get_store_stats()
    return {"success": True, "message": "Task statistics", **stats}


# ============================================================
# OpenAI-compatible tool registry
# ============================================================

TOOL_REGISTRY: list[dict] = [
    CREATE_TASK_SCHEMA,
    LIST_TASKS_SCHEMA,
    CLOSE_TASK_SCHEMA,
]

TOOL_FUNCTIONS: dict[str, callable] = {
    "create_inspection_task": create_inspection_task,
    "list_inspection_tasks": list_inspection_tasks,
    "close_inspection_task": close_inspection_task,
}
