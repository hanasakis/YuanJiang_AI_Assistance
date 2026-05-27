"""Tests for src/tools/ — inspection task creation and management.

Tests use a temp JSON store, never touching data/runtime/.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.tools.schemas import (
    CREATE_TASK_SCHEMA,
    CLOSE_TASK_SCHEMA,
    LIST_TASKS_SCHEMA,
    InspectionTaskCreate,
    InspectionTaskResult,
    TaskStatusUpdate,
)
from src.tools.task_store import (
    close_task,
    create_task,
    get_store_stats,
    get_task,
    list_open_tasks,
    list_tasks,
    update_task,
)
from src.tools.inspection_tools import (
    close_inspection_task,
    create_inspection_task,
    list_inspection_tasks,
    list_open_tasks as tool_list_open,
)


# ============================================================
# Pydantic schemas
# ============================================================

class TestSchemas:
    def test_valid_task_create(self):
        t = InspectionTaskCreate(
            task_type="delivery_risk",
            priority="P1",
            target_id="seller_A",
            title="Delay risk for seller_A",
            description="delay_rate=23%, exceeds 15% P1 threshold",
            sop_reference="SOP-DELIVERY-001 1.2",
            assignee="area_manager",
        )
        assert t.task_type == "delivery_risk"
        assert t.priority == "P1"

    def test_invalid_task_type_raises(self):
        with pytest.raises(ValueError):
            InspectionTaskCreate(
                task_type="invalid_type",
                priority="P0",
                target_id="x",
                title="Test",
                description="Test",
            )

    def test_invalid_priority_raises(self):
        with pytest.raises(ValueError):
            InspectionTaskCreate(
                task_type="delivery_risk",
                priority="P5",
                target_id="x",
                title="Test",
                description="Test",
            )

    def test_empty_title_raises(self):
        with pytest.raises(ValueError):
            InspectionTaskCreate(
                task_type="delivery_risk",
                priority="P0",
                target_id="x",
                title="",
                description="Test",
            )

    def test_openai_schemas_have_required_fields(self):
        assert "name" in CREATE_TASK_SCHEMA
        assert "parameters" in CREATE_TASK_SCHEMA
        assert "required" in CREATE_TASK_SCHEMA["parameters"]
        assert "task_type" in CREATE_TASK_SCHEMA["parameters"]["required"]

        assert "name" in CLOSE_TASK_SCHEMA
        assert "name" in LIST_TASKS_SCHEMA

    def test_inspection_task_result_defaults(self):
        r = InspectionTaskResult(success=True, message="Done")
        assert r.success
        assert r.task_id is None
        assert r.task is None


# ============================================================
# Task store (persistence)
# ============================================================

class TestTaskStore:
    @pytest.fixture
    def store(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp) / "tasks.json"

    def test_create_and_retrieve(self, store):
        t = create_task(
            InspectionTaskCreate(
                task_type="delivery_risk",
                priority="P0",
                target_id="seller_A",
                title="Critical delay",
                description="delay_rate > 30%",
            ),
            store_path=store,
        )
        assert t.task_id.startswith("YJ-")
        assert "-" in t.task_id
        assert t.status == "pending"

        retrieved = get_task(t.task_id, store_path=store)
        assert retrieved is not None
        assert retrieved.task_id == t.task_id
        assert retrieved.priority == "P0"

    def test_get_nonexistent_task(self, store):
        assert get_task("YJ-20990101-9999", store_path=store) is None

    def test_task_id_increments(self, store):
        t1 = create_task(
            InspectionTaskCreate(
                task_type="delivery_risk", priority="P1",
                target_id="s1", title="T1", description="D1",
            ),
            store_path=store,
        )
        t2 = create_task(
            InspectionTaskCreate(
                task_type="review_triage", priority="P2",
                target_id="s2", title="T2", description="D2",
            ),
            store_path=store,
        )
        seq1 = int(t1.task_id.split("-")[-1])
        seq2 = int(t2.task_id.split("-")[-1])
        assert seq2 == seq1 + 1

    def test_list_filters(self, store):
        create_task(
            InspectionTaskCreate(
                task_type="delivery_risk", priority="P1",
                target_id="s1", title="T1", description="D1",
                assignee="alice",
            ),
            store_path=store,
        )
        create_task(
            InspectionTaskCreate(
                task_type="review_triage", priority="P2",
                target_id="s2", title="T2", description="D2",
                assignee="bob",
            ),
            store_path=store,
        )

        all_tasks = list_tasks(store_path=store)
        assert len(all_tasks) == 2

        filtered = list_tasks(priority="P1", store_path=store)
        assert len(filtered) == 1
        assert filtered[0].assignee == "alice"

        filtered2 = list_tasks(assignee="bob", store_path=store)
        assert len(filtered2) == 1

    def test_list_open_tasks(self, store):
        t1 = create_task(
            InspectionTaskCreate(
                task_type="delivery_risk", priority="P0",
                target_id="s1", title="T1", description="D1",
            ),
            store_path=store,
        )
        t2 = create_task(
            InspectionTaskCreate(
                task_type="review_triage", priority="P1",
                target_id="s2", title="T2", description="D2",
            ),
            store_path=store,
        )

        open_tasks = list_open_tasks(store_path=store)
        assert len(open_tasks) == 2
        assert open_tasks[0].priority == "P0"  # P0 first

        # Close t1
        close_task(t1.task_id, resolution_note="Resolved", store_path=store)

        open_tasks = list_open_tasks(store_path=store)
        assert len(open_tasks) == 1
        assert open_tasks[0].task_id == t2.task_id

    def test_update_task_status(self, store):
        t = create_task(
            InspectionTaskCreate(
                task_type="delivery_risk", priority="P0",
                target_id="s1", title="T1", description="D1",
            ),
            store_path=store,
        )

        update = TaskStatusUpdate(
            task_id=t.task_id,
            status="in_progress",
            assignee="charlie",
        )
        updated = update_task(update, store_path=store)
        assert updated is not None
        assert updated.status == "in_progress"
        assert updated.assignee == "charlie"

    def test_close_task_with_note(self, store):
        t = create_task(
            InspectionTaskCreate(
                task_type="delivery_risk", priority="P0",
                target_id="s1", title="T1", description="D1",
            ),
            store_path=store,
        )

        closed = close_task(t.task_id, "Fixed in review", store_path=store)
        assert closed is not None
        assert closed.status == "resolved"
        assert closed.resolution_note == "Fixed in review"
        assert closed.resolved_at is not None

    def test_update_nonexistent_task(self, store):
        update = TaskStatusUpdate(task_id="YJ-20990101-9999", status="resolved")
        result = update_task(update, store_path=store)
        assert result is None

    def test_get_store_stats(self, store):
        create_task(
            InspectionTaskCreate(
                task_type="delivery_risk", priority="P0",
                target_id="s1", title="T1", description="D1",
            ),
            store_path=store,
        )
        create_task(
            InspectionTaskCreate(
                task_type="review_triage", priority="P1",
                target_id="s2", title="T2", description="D2",
            ),
            store_path=store,
        )

        stats = get_store_stats(store_path=store)
        assert stats["total"] == 2
        assert stats["by_status"]["pending"] == 2
        assert "delivery_risk" in stats["by_type"]

    def test_empty_store(self, store):
        assert list_tasks(store_path=store) == []
        assert list_open_tasks(store_path=store) == []


# ============================================================
# Inspection tools (function-callable wrappers)
# ============================================================

class TestInspectionTools:
    @pytest.fixture
    def store(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp) / "tasks.json"

    def _store_arg(self, store):
        return str(store)

    def test_create_tool_returns_success(self, store):
        result = create_inspection_task(
            task_type="delivery_risk",
            priority="P1",
            target_id="seller_A",
            title="Delay risk",
            description="delay_rate=23%",
        )
        assert result["success"]
        assert result["task_id"].startswith("YJ-")

    def test_create_tool_validation_error(self, store):
        result = create_inspection_task(
            task_type="invalid_xyz",
            priority="P1",
            target_id="x",
            title="Test",
            description="Test",
        )
        assert not result["success"]
        assert "Validation" in result["message"]

    def test_list_tool_returns_tasks(self, store):
        create_inspection_task(
            task_type="delivery_risk", priority="P1",
            target_id="s1", title="T1", description="D1",
        )
        result = list_inspection_tasks(status="pending")
        assert result["success"]
        assert result["count"] >= 1
        assert "tasks" in result

    def test_list_open_tool(self, store):
        create_inspection_task(
            task_type="delivery_risk", priority="P0",
            target_id="s1", title="T1", description="D1",
        )
        result = tool_list_open()
        assert result["success"]
        assert result["count"] >= 1

    def test_close_tool_works(self, store):
        r = create_inspection_task(
            task_type="delivery_risk", priority="P0",
            target_id="s1", title="T1", description="D1",
        )
        tid = r["task_id"]

        result = close_inspection_task(
            task_id=tid,
            status="resolved",
            resolution_note="All clear",
        )
        assert result["success"]
        assert result["task_id"] == tid

    def test_close_tool_invalid_status(self, store):
        r = create_inspection_task(
            task_type="delivery_risk", priority="P0",
            target_id="s1", title="T1", description="D1",
        )
        result = close_inspection_task(
            task_id=r["task_id"],
            status="deleted",  # invalid
        )
        assert not result["success"]

    def test_close_nonexistent_task(self, store):
        result = close_inspection_task(task_id="YJ-20990101-9999")
        assert not result["success"]
