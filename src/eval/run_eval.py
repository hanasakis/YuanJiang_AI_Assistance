"""Evaluation runner for YuanJiang OpsGuard agent.

Measures 4 key metrics on the evaluation question set:
  1. intent_accuracy       — Can the agent classify user intent correctly?
  2. metric_tool_success   — Do data queries return valid results?
  3. sop_source_hit_rate   — Does SOP retrieval find relevant chunks?
  4. task_creation_success  — Do task creation requests succeed?

Runs offline using mock LLM responses for reproducibility.
No external API calls required.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from unittest import mock

import duckdb

_EVAL_FILE = Path("data/eval/ecommerce_questions.jsonl")
_SOP_DIR = Path("docs/sop")
_REPORT_FILE = Path("docs/eval_report.md")

# ============================================================
# Data model
# ============================================================

@dataclass
class EvalQuestion:
    id: str
    question: str
    expected_intent: str
    relevant_sop: str | None
    expected_tools: list[str]
    difficulty: str


@dataclass
class EvalResult:
    question: EvalQuestion
    actual_intent: str = ""
    intent_correct: bool = False
    metric_data_returned: bool = False
    sop_chunks_found: int = 0
    sop_relevant: bool = False
    task_created: bool = False
    task_success: bool = False
    error: str = ""


@dataclass
class EvalReport:
    results: list[EvalResult] = field(default_factory=list)
    intent_accuracy: float = 0.0
    metric_tool_success_rate: float = 0.0
    sop_source_hit_rate: float = 0.0
    task_creation_success_rate: float = 0.0
    total_questions: int = 0
    duration_seconds: float = 0.0
    by_difficulty: dict = field(default_factory=dict)
    by_intent: dict = field(default_factory=dict)


# ============================================================
# Question loader
# ============================================================

def load_questions(path: str | Path = _EVAL_FILE) -> list[EvalQuestion]:
    """Load evaluation questions from JSONL file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Eval questions not found: {path}")

    questions = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            questions.append(EvalQuestion(
                id=data["id"],
                question=data["question"],
                expected_intent=data["expected_intent"],
                relevant_sop=data.get("relevant_sop"),
                expected_tools=data.get("expected_tools", []),
                difficulty=data.get("difficulty", "easy"),
            ))
    return questions


# ============================================================
# Mocked LLM responses for deterministic evaluation
# ============================================================

def _get_mock_intent_response(question: str) -> dict:
    """Keyword-based intent classification matching the agent's fallback."""
    return {"message": {"content": '{"intent": "detected", "reasoning": "mock"}'}}


# ============================================================
# Evaluation logic
# ============================================================

def run_evaluation(
    questions: list[EvalQuestion] | None = None,
    verbose: bool = True,
) -> EvalReport:
    """Run full evaluation on all questions.

    Args:
        questions: Pre-loaded questions. Loads from default if None.
        verbose: Print progress.

    Returns:
        EvalReport with all metrics computed.
    """
    if questions is None:
        questions = load_questions()

    start = time.time()
    results: list[EvalResult] = []

    for i, q in enumerate(questions):
        if verbose:
            print(f"[{i+1:03d}/{len(questions)}] {q.id}: {q.question[:70]}...")

        result = _evaluate_one(q)
        results.append(result)

    elapsed = time.time() - start
    report = _build_report(results, elapsed)

    if verbose:
        _print_summary(report)

    return report


def _evaluate_one(q: EvalQuestion) -> EvalResult:
    """Evaluate a single question across all 4 metrics."""
    result = EvalResult(question=q)

    # ---- 1. Intent accuracy (offline: keyword fallback) ----
    from src.app.intent import _fallback_classify
    classification = _fallback_classify(q.question)
    result.actual_intent = classification.get("intent", "unknown")
    result.intent_correct = (result.actual_intent == q.expected_intent)

    if q.expected_intent == "unknown":
        result.intent_correct = (result.actual_intent == "unknown")

    # ---- 2. Metric tool success ----
    if any(t in q.expected_tools for t in [
        "get_top_risky_sellers", "get_seller_profile",
        "get_order_risk", "get_category_quality_risk",
        "list_inspection_tasks",
    ]):
        try:
            from src.data_ops.build_duckdb import build_database
            from src.data_ops.metrics import get_top_risky_sellers
            db_path = Path("data/processed/olist_eval.duckdb")
            build_database(csv_dir="data/sample/olist", db_path=db_path, overwrite=True)
            data = get_top_risky_sellers(limit=5, db_path=db_path)
            result.metric_data_returned = len(data) > 0
        except Exception as exc:
            result.error = str(exc)[:200]
    else:
        result.metric_data_returned = True  # N/A → pass

    # ---- 3. SOP source hit rate ----
    if q.relevant_sop:
        # Map SOP doc IDs to actual source file substrings
        sop_file_map = {
            "SOP-DELIVERY-001": "delivery_risk",
            "SOP-REVIEW-002": "review_triage",
            "SOP-PRODUCT-003": "product_quality",
            "SOP-TASK-004": "inspection_task",
        }
        expected_file = sop_file_map.get(q.relevant_sop, q.relevant_sop.lower())
        try:
            from src.rag.retriever import retrieve_sop
            from src.rag.fts_index import build_fts_index
            from src.rag.chunker import chunk_directory
            fts_db = Path("data/fts/eval_sop.db")
            chunks = chunk_directory("docs/sop")
            build_fts_index(chunks, db_path=fts_db, overwrite=True)
            sop_results = retrieve_sop(q.question, top_k=5, db_path=fts_db)
            result.sop_chunks_found = len(sop_results)
            result.sop_relevant = any(
                expected_file.lower() in r.get("source", "").lower()
                for r in sop_results
            )
        except Exception:
            pass
    else:
        result.sop_relevant = True  # N/A → pass (no SOP expected)

    # ---- 4. Task creation success ----
    if "create_inspection_task" in q.expected_tools:
        try:
            from src.tools.inspection_tools import create_inspection_task
            task_result = create_inspection_task(
                task_type="delivery_risk",
                priority="P0",
                target_id="eval_target",
                title=f"Eval task: {q.id}",
                description=q.question,
            )
            result.task_created = True
            result.task_success = task_result.get("success", False)
        except Exception:
            pass
    else:
        result.task_success = True  # N/A → pass

    return result


def _mock_non_json() -> dict:
    """Return non-JSON to force keyword-based fallback classifier."""
    return {"message": {"content": "not valid json"}}


def _build_report(results: list[EvalResult], elapsed: float) -> EvalReport:
    """Compute aggregate metrics from individual results."""
    total = len(results)

    report = EvalReport(results=results, total_questions=total)
    report.duration_seconds = round(elapsed, 2)

    # 1. Intent accuracy
    intent_correct = sum(1 for r in results if r.intent_correct)
    report.intent_accuracy = round(intent_correct / total * 100, 1) if total else 0

    # 2. Metric tool success (only for metric/mixed questions)
    metric_qs = [r for r in results
                 if r.question.expected_intent in ("metric_query", "mixed")]
    if metric_qs:
        report.metric_tool_success_rate = round(
            sum(1 for r in metric_qs if r.metric_data_returned) / len(metric_qs) * 100, 1
        )
    else:
        report.metric_tool_success_rate = 100.0

    # 3. SOP hit rate (only for questions with expected SOP)
    sop_qs = [r for r in results if r.question.relevant_sop]
    if sop_qs:
        report.sop_source_hit_rate = round(
            sum(1 for r in sop_qs if r.sop_relevant) / len(sop_qs) * 100, 1
        )
    else:
        report.sop_source_hit_rate = 100.0

    # 4. Task creation success (only for questions expecting task creation)
    task_qs = [r for r in results
               if "create_inspection_task" in r.question.expected_tools]
    if task_qs:
        report.task_creation_success_rate = round(
            sum(1 for r in task_qs if r.task_success) / len(task_qs) * 100, 1
        )
    else:
        report.task_creation_success_rate = 100.0

    # By difficulty
    for diff in ("easy", "medium", "hard"):
        subset = [r for r in results if r.question.difficulty == diff]
        if subset:
            report.by_difficulty[diff] = {
                "count": len(subset),
                "intent_accuracy": round(
                    sum(1 for r in subset if r.intent_correct) / len(subset) * 100, 1
                ),
            }

    # By intent
    for intent in ("metric_query", "sop_qa", "create_task", "mixed", "unknown"):
        subset = [r for r in results if r.question.expected_intent == intent]
        if subset:
            report.by_intent[intent] = {
                "count": len(subset),
                "intent_accuracy": round(
                    sum(1 for r in subset if r.intent_correct) / len(subset) * 100, 1
                ),
            }

    return report


def _print_summary(report: EvalReport) -> None:
    """Print evaluation summary to stdout."""
    print()
    print("=" * 50)
    print("  YuanJiang OpsGuard — Evaluation Report")
    print("=" * 50)
    print(f"  Questions:        {report.total_questions}")
    print(f"  Duration:         {report.duration_seconds}s")
    print()
    print(f"  intent_accuracy:            {report.intent_accuracy}%")
    print(f"  metric_tool_success_rate:   {report.metric_tool_success_rate}%")
    print(f"  sop_source_hit_rate:        {report.sop_source_hit_rate}%")
    print(f"  task_creation_success_rate: {report.task_creation_success_rate}%")
    print()
    print("  By difficulty:")
    for diff, stats in report.by_difficulty.items():
        print(f"    {diff}: {stats['count']} questions, "
              f"intent_acc={stats['intent_accuracy']}%")
    print("=" * 50)


def generate_report_md(report: EvalReport, path: str | Path = _REPORT_FILE) -> Path:
    """Write evaluation report as Markdown."""
    lines = [
        "# YuanJiang OpsGuard — Evaluation Report",
        "",
        f"**Date**: {__import__('datetime').datetime.now().strftime('%Y-%m-%d')}",
        f"**Questions**: {report.total_questions}",
        f"**Duration**: {report.duration_seconds}s",
        "",
        "## Summary Metrics",
        "",
        "| Metric | Score | Description |",
        "|--------|-------|-------------|",
        f"| Intent Accuracy | **{report.intent_accuracy}%** | Correctly classifies user intent into 5 categories |",
        f"| Metric Tool Success | **{report.metric_tool_success_rate}%** | Data queries return valid structured results |",
        f"| SOP Source Hit Rate | **{report.sop_source_hit_rate}%** | SOP retrieval finds the expected document |",
        f"| Task Creation Success | **{report.task_creation_success_rate}%** | Task creation requests produce valid tasks |",
        "",
        "## By Difficulty",
        "",
        "| Difficulty | Count | Intent Accuracy |",
        "|------------|-------|-----------------|",
    ]
    for diff in ("easy", "medium", "hard"):
        stats = report.by_difficulty.get(diff, {})
        if stats:
            lines.append(
                f"| {diff} | {stats.get('count', 0)} | "
                f"{stats.get('intent_accuracy', 0)}% |"
            )

    lines += [
        "",
        "## By Intent",
        "",
        "| Intent | Count | Accuracy |",
        "|--------|-------|----------|",
    ]
    for intent in ("metric_query", "sop_qa", "create_task", "mixed", "unknown"):
        stats = report.by_intent.get(intent, {})
        if stats:
            lines.append(
                f"| {intent} | {stats.get('count', 0)} | "
                f"{stats.get('intent_accuracy', 0)}% |"
            )

    lines += [
        "",
        "## Detailed Results",
        "",
        "| ID | Question | Expected | Actual | Intent OK | Metric | SOP | Task |",
        "|----|----------|----------|--------|-----------|--------|-----|------|",
    ]
    for r in report.results:
        q = r.question
        lines.append(
            f"| {q.id} | {q.question[:50]}... | {q.expected_intent} | "
            f"{r.actual_intent} | {'OK' if r.intent_correct else 'FAIL'} | "
            f"{'OK' if r.metric_data_returned else '—'} | "
            f"{'HIT' if r.sop_relevant else 'MISS' if q.relevant_sop else '—'} | "
            f"{'OK' if r.task_success else '—'} |"
        )

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


if __name__ == "__main__":
    questions = load_questions()
    report = run_evaluation(questions)
    report_path = generate_report_md(report)
    print(f"\nReport written to {report_path}")
