"""Pydantic schemas for inspection task tools.

These schemas define the contract between the Agent (LLM function calling)
and the task execution layer. Every tool input and output is validated.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# ============================================================
# Enums / Literals
# ============================================================

TaskType = Literal["delivery_risk", "review_triage", "quality_inspection"]
Priority = Literal["P0", "P1", "P2", "P3"]
TaskStatus = Literal["pending", "in_progress", "resolved", "closed", "ignored"]

_VALID_PRIORITIES: set[str] = {"P0", "P1", "P2", "P3"}
_VALID_TYPES: set[str] = {"delivery_risk", "review_triage", "quality_inspection"}


# ============================================================
# Request schemas
# ============================================================

class InspectionTaskCreate(BaseModel):
    """Input schema for creating an inspection task."""

    task_type: TaskType = Field(
        ...,
        description="Type of inspection: delivery_risk, review_triage, or quality_inspection",
    )
    priority: Priority = Field(
        ...,
        description="Priority: P0 (critical/4h), P1 (important/24h), P2 (watch/week), P3 (observe)",
    )
    target_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Seller ID or Product ID to inspect",
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Human-readable task title",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Detailed task description with findings and data",
    )
    sop_reference: str = Field(
        default="",
        max_length=512,
        description="SOP clause reference, e.g. SOP-DELIVERY-001 1.2",
    )
    assignee: str = Field(
        default="",
        max_length=128,
        description="Assigned person or role (e.g. area_manager, qc_team)",
    )

    @field_validator("task_type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in _VALID_TYPES:
            raise ValueError(f"Invalid task_type: {v}. Must be one of {_VALID_TYPES}")
        return v

    @field_validator("priority")
    @classmethod
    def _check_priority(cls, v: str) -> str:
        if v not in _VALID_PRIORITIES:
            raise ValueError(f"Invalid priority: {v}. Must be one of {_VALID_PRIORITIES}")
        return v


class TaskStatusUpdate(BaseModel):
    """Input schema for updating a task's status."""

    task_id: str = Field(..., min_length=1, description="Task ID to update")
    status: TaskStatus = Field(..., description="New status")
    resolution_note: str = Field(
        default="",
        max_length=4096,
        description="Explanation of resolution or reason for closing",
    )
    assignee: str | None = Field(
        default=None,
        max_length=128,
        description="Reassign to a new person or role",
    )


# ============================================================
# Response schemas
# ============================================================

class InspectionTask(BaseModel):
    """Complete stored task record."""

    task_id: str = Field(..., description="Unique task ID: YJ-YYYYMMDD-NNNN")
    task_type: TaskType
    priority: Priority
    status: TaskStatus = Field(default="pending")
    target_id: str
    title: str
    description: str
    sop_reference: str = ""
    assignee: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    resolved_at: str | None = None
    resolution_note: str = ""

    def to_openai_schema(self) -> dict:
        """Return a simplified dict for LLM consumption."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "priority": self.priority,
            "status": self.status,
            "target_id": self.target_id,
            "title": self.title,
            "assignee": self.assignee,
            "created_at": self.created_at,
        }


class InspectionTaskResult(BaseModel):
    """Result of a task operation (create / update / close)."""

    success: bool = Field(..., description="Whether the operation succeeded")
    task_id: str | None = Field(default=None, description="Affected task ID")
    message: str = Field(default="", description="Human-readable result")
    task: InspectionTask | None = Field(default=None, description="Full task record")


# ============================================================
# OpenAI-compatible function calling schemas
# ============================================================

CREATE_TASK_SCHEMA: dict = {
    "name": "create_inspection_task",
    "description": (
        "Create a new inspection task for a seller or product risk. "
        "Use when the Agent identifies a risk that needs tracking and resolution."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_type": {
                "type": "string",
                "enum": list(_VALID_TYPES),
                "description": "Type of inspection task",
            },
            "priority": {
                "type": "string",
                "enum": list(_VALID_PRIORITIES),
                "description": "P0=critical/4h, P1=important/24h, P2=watch/week, P3=observe",
            },
            "target_id": {
                "type": "string",
                "description": "Seller ID or Product ID",
            },
            "title": {
                "type": "string",
                "description": "Task title",
            },
            "description": {
                "type": "string",
                "description": "Detailed description with data findings",
            },
            "sop_reference": {
                "type": "string",
                "description": "SOP clause reference",
            },
            "assignee": {
                "type": "string",
                "description": "Assigned person or role",
            },
        },
        "required": ["task_type", "priority", "target_id", "title", "description"],
    },
}

LIST_TASKS_SCHEMA: dict = {
    "name": "list_inspection_tasks",
    "description": "List inspection tasks with optional filters.",
    "parameters": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "resolved", "closed", "ignored"],
                "description": "Filter by status",
            },
            "task_type": {
                "type": "string",
                "enum": list(_VALID_TYPES),
                "description": "Filter by task type",
            },
            "priority": {
                "type": "string",
                "enum": list(_VALID_PRIORITIES),
                "description": "Filter by priority",
            },
            "assignee": {
                "type": "string",
                "description": "Filter by assignee",
            },
            "limit": {
                "type": "integer",
                "description": "Max results (default 20)",
            },
        },
    },
}

CLOSE_TASK_SCHEMA: dict = {
    "name": "close_inspection_task",
    "description": "Close or resolve an inspection task.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "Task ID to close",
            },
            "status": {
                "type": "string",
                "enum": ["resolved", "closed", "ignored"],
                "description": "Target status",
            },
            "resolution_note": {
                "type": "string",
                "description": "Resolution explanation",
            },
        },
        "required": ["task_id", "status"],
    },
}
