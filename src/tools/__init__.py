"""tools — Inspection task tools with Pydantic schemas for LangGraph function calling.

Tools provided:
- query_seller_risk: compute risk scores per seller
- query_logistics_delay: find orders exceeding SLA thresholds
- query_negative_reviews: surface low-score reviews with text
- create_inspection_task: write a trackable task to SQLite
- list_inspection_tasks: query tasks by status / assignee / date
- update_inspection_task: close or reassign a task

Each tool exposes an OpenAI-compatible function-calling JSON schema.
"""

__all__: list[str] = []
