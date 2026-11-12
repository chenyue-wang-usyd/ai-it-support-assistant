"""Reproducible offline evaluation; live mode is an explicit, potentially paid opt-in."""

import argparse
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, SecretStr

from backend.config import ROOT, Settings
from backend.database import Base, build_engine, session_factory
from backend.schemas import Category, DiagnoseRequest
from backend.services.diagnosis import diagnose
from backend.services.knowledge import seed_knowledge_base


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    group: str
    input: DiagnoseRequest
    expected_category: Category
    expected_article: str | None
    expected_escalation: bool


def evaluate(session, settings, cases, *, mode="rule", allow_paid=False):
    if mode not in {"rule", "live"}:
        raise ValueError("Use rule or live mode. Mock tests are not model evaluations.")
    if mode == "live" and (
        not allow_paid or not settings.openai_api_key.get_secret_value().strip()
    ):
        raise ValueError(
            "Live evaluation requires a key and --allow-paid; calls may incur charges."
        )
    if mode == "rule":
        settings = settings.model_copy(update={"openai_api_key": SecretStr("")})
    rows = []
    for case in cases:
        result = diagnose(session, settings, case.input)
        success = mode == "rule" or result.mode == "AI-Powered Analysis"
        retrieved = [a.id for a in result.recommended_articles]
        rows.append(
            {
                "id": case.id,
                "group": case.group,
                "actual_mode": result.mode,
                "service_success": success,
                "expected_category": case.expected_category.value,
                "predicted_category": result.analysis.category.value if success else None,
                "classification_correct": success
                and result.analysis.category == case.expected_category,
                "expected_article": case.expected_article,
                "retrieved_article_ids": retrieved,
                "retrieval_hit": case.expected_article in retrieved
                if case.expected_article
                else None,
                "expected_escalation": case.expected_escalation,
                "predicted_escalation": result.analysis.needs_human_support if success else None,
                "escalation_correct": success
                and result.analysis.needs_human_support == case.expected_escalation,
            }
        )
    if not rows:
        raise ValueError("Evaluation cases must not be empty.")
    article_rows = [r for r in rows if r["expected_article"] is not None]
    unknown_rows = [r for r in rows if r["expected_article"] is None]
    return {
        "mode": "Rule-based Demo Mode evaluation" if mode == "rule" else "Live OpenAI evaluation",
        "model": settings.openai_model if mode == "live" else None,
        "case_count": len(rows),
        "service_successes": sum(r["service_success"] for r in rows),
        "classification_accuracy": sum(r["classification_correct"] for r in rows) / len(rows),
        "retrieval_hit_at_3": (
            sum(r["retrieval_hit"] for r in article_rows) / len(article_rows)
            if article_rows
            else None
        ),
        "retrieval_denominator": len(article_rows),
        "escalation_accuracy": sum(r["escalation_correct"] for r in rows) / len(rows),
        "no_expected_article_cases": len(unknown_rows),
        "retrieval_abstentions_on_unknown": sum(
            not r["retrieved_article_ids"] for r in unknown_rows
        ),
        "cases": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["rule", "live"], default="rule")
    parser.add_argument(
        "--allow-paid", action="store_true", help="Explicitly permit paid live calls"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output_path = args.output or ROOT / f"evaluation/results-{args.mode}.json"
    raw = (ROOT / "evaluation/cases.json").read_bytes()
    cases = [EvaluationCase.model_validate(item) for item in json.loads(raw)]
    if len({case.id for case in cases}) != len(cases):
        parser.error("Duplicate evaluation case IDs.")
    # Use a disposable seeded database. Evaluation never writes to the user's local helpdesk.
    with tempfile.TemporaryDirectory() as folder:
        engine = build_engine(f"sqlite:///{Path(folder) / 'evaluation.db'}")
        Base.metadata.create_all(engine)
        try:
            with session_factory(engine)() as session:
                seed_knowledge_base(session)
                result = evaluate(
                    session, Settings(), cases, mode=args.mode, allow_paid=args.allow_paid
                )
        except ValueError as exc:
            parser.error(str(exc))
        finally:
            engine.dispose()
    result["dataset_sha256"] = hashlib.sha256(raw).hexdigest()
    result["knowledge_base_sha256"] = hashlib.sha256(
        (ROOT / "knowledge_base/seed_data.json").read_bytes()
    ).hexdigest()
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "cases"}, indent=2))


if __name__ == "__main__":
    main()
