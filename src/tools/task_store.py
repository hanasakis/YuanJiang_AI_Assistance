"""Task persistence layer — JSON file in data/runtime/.

data/runtime/ is gitignored. Tasks are stored as a flat JSON array.
Atomic writes prevent corruption on concurrent access.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from src.tools.schemas import InspectionTask, InspectionTaskCreate, TaskStatusUpdate

_DEFAULT_PATH = Path("data/runtime/tasks.json")
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_task_id(store_path: Path) -> str:
    """Generate a stable task ID: YJ-YYYYMMDD-NNNN."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"YJ-{today}-"

    tasks = _read_all(store_path)
    today_tasks = [t for t in tasks if t["task_id"].startswith(prefix)]
    max_seq = 0
    for t in today_tasks:
        try:
            seq = int(t["task_id"].split("-")[-1])
            max_seq = max(max_seq, seq)
        except (ValueError, IndexError):
            pass

    return f"{prefix}{max_seq + 1:04d}"


def _read_all(store_path: Path) -> list[dict]:
    """Read all tasks from the JSON store. Returns [] if file missing."""
    if not store_path.exists():
        return []
    try:
        return json.loads(store_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _write_all(store_path: Path, tasks: list[dict]) -> None:
    """Atomically write all tasks to the JSON store."""
    store_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = store_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(store_path)  # atomic on same filesystem


# ============================================================
# Public API
# ============================================================

def create_task(
    task_input: InspectionTaskCreate,
    store_path: str | Path = _DEFAULT_PATH,
) -> InspectionTask:
    """Create a new inspection task and persist it.

    Args:
        task_input: Validated Pydantic schema for task creation.
        store_path: Path to the JSON task store.

    Returns:
        The full InspectionTask record with generated task_id.
    """
    store_path = Path(store_path)

    with _lock:
        task_id = _generate_task_id(store_path)
        now = _now()

        task = InspectionTask(
            task_id=task_id,
            task_type=task_input.task_type,
            priority=task_input.priority,
            status="pending",
            target_id=task_input.target_id,
            title=task_input.title,
            description=task_input.description,
            sop_reference=task_input.sop_reference,
            assignee=task_input.assignee,
            created_at=now,
            updated_at=now,
        )

        tasks = _read_all(store_path)
        tasks.append(task.model_dump())
        _write_all(store_path, tasks)

        return task


def get_task(
    task_id: str,
    store_path: str | Path = _DEFAULT_PATH,
) -> InspectionTask | None:
    """Retrieve a single task by ID."""
    tasks = _read_all(Path(store_path))
    for t in tasks:
        if t["task_id"] == task_id:
            return InspectionTask(**t)
    return None


def list_tasks(
    status: str | None = None,
    task_type: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
    limit: int = 20,
    store_path: str | Path = _DEFAULT_PATH,
) -> list[InspectionTask]:
    """List tasks with optional filters.

    Args:
        status: Filter by status (pending, in_progress, resolved, closed, ignored).
        task_type: Filter by task type.
        priority: Filter by priority (P0-P3).
        assignee: Filter by assignee (partial match).
        limit: Max number of tasks to return.
        store_path: Path to the JSON task store.

    Returns:
        List of InspectionTask records, newest first.
    """
    tasks = _read_all(Path(store_path))
    results: list[InspectionTask] = []

    for t in reversed(tasks):  # newest first
        task = InspectionTask(**t)
        if status and task.status != status:
            continue
        if task_type and task.task_type != task_type:
            continue
        if priority and task.priority != priority:
            continue
        if assignee and assignee.lower() not in task.assignee.lower():
            continue
        results.append(task)
        if len(results) >= limit:
            break

    return results


def list_open_tasks(
    store_path: str | Path = _DEFAULT_PATH,
) -> list[InspectionTask]:
    """Return all open (non-closed, non-resolved) tasks, P0 first."""
    tasks = _read_all(Path(store_path))
    open_tasks = [
        InspectionTask(**t)
        for t in tasks
        if t["status"] in ("pending", "in_progress")
    ]
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    open_tasks.sort(key=lambda t: priority_order.get(t.priority, 99))
    return open_tasks


def update_task(
    update: TaskStatusUpdate,
    store_path: str | Path = _DEFAULT_PATH,
) -> InspectionTask | None:
    """Update a task's status and optionally reassign.

    Args:
        update: Validated status update schema.
        store_path: Path to the JSON task store.

    Returns:
        Updated InspectionTask, or None if task_id not found.
    """
    store_path = Path(store_path)

    with _lock:
        tasks = _read_all(store_path)
        for i, t in enumerate(tasks):
            if t["task_id"] == update.task_id:
                task = InspectionTask(**t)
                task.status = update.status
                task.updated_at = _now()

                if update.status in ("resolved", "closed"):
                    task.resolved_at = _now()
                if update.resolution_note:
                    task.resolution_note = update.resolution_note
                if update.assignee is not None:
                    task.assignee = update.assignee

                tasks[i] = task.model_dump()
                _write_all(store_path, tasks)
                return task

        return None


def close_task(
    task_id: str,
    resolution_note: str = "",
    store_path: str | Path = _DEFAULT_PATH,
) -> InspectionTask | None:
    """Close a task as resolved.

    Convenience wrapper around update_task with status='resolved'.

    Args:
        task_id: Task ID to close.
        resolution_note: Explanation of resolution.
        store_path: Path to the JSON task store.

    Returns:
        Updated InspectionTask, or None if not found.
    """
    update = TaskStatusUpdate(
        task_id=task_id,
        status="resolved",
        resolution_note=resolution_note,
    )
    return update_task(update, store_path)


def get_store_stats(store_path: str | Path = _DEFAULT_PATH) -> dict:
    """Return aggregate statistics about the task store."""
    tasks = _read_all(Path(store_path))
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_priority: dict[str, int] = {}

    for t in tasks:
        s = t.get("status", "unknown")
        tp = t.get("task_type", "unknown")
        p = t.get("priority", "unknown")
        by_status[s] = by_status.get(s, 0) + 1
        by_type[tp] = by_type.get(tp, 0) + 1
        by_priority[p] = by_priority.get(p, 0) + 1

    return {
        "total": len(tasks),
        "by_status": by_status,
        "by_type": by_type,
        "by_priority": by_priority,
    }
