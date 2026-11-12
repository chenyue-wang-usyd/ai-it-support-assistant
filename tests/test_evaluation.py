import json

import pytest

from backend.config import ROOT
from evaluation.run import EvaluationCase, evaluate


def test_dataset_coverage_and_reproducible_rule_evaluation(client):
    cases = [
        EvaluationCase.model_validate(row)
        for row in json.loads((ROOT / "evaluation/cases.json").read_text(encoding="utf-8"))
    ]
    assert len(cases) >= 20
    assert len({case.id for case in cases}) == len(cases)
    assert {case.group for case in cases} >= {
        "Wi-Fi",
        "Hardware",
        "Software",
        "Account",
        "Email",
        "VPN",
        "Ambiguous",
        "Unknown",
    }
    with client.app.state.sessions() as session:
        first = evaluate(session, client.app.state.settings, cases)
        assert first == evaluate(session, client.app.state.settings, cases)
    assert first["mode"] == "Rule-based Demo Mode evaluation"
    assert first["classification_accuracy"] == sum(
        row["classification_correct"] for row in first["cases"]
    ) / len(cases)
    assert first["retrieval_denominator"] == sum(c.expected_article is not None for c in cases)
    assert first["service_successes"] == len(cases)
    assert client.get("/stats").json()["total_tickets"] == 0


def test_live_evaluation_requires_explicit_paid_opt_in(client):
    with client.app.state.sessions() as session:
        with pytest.raises(ValueError, match="requires a key"):
            evaluate(session, client.app.state.settings, [], mode="live")
        with pytest.raises(ValueError, match="Mock tests"):
            evaluate(session, client.app.state.settings, [], mode="mock")
        with pytest.raises(ValueError, match="must not be empty"):
            evaluate(session, client.app.state.settings, [])


def test_live_fallback_is_not_counted_as_model_accuracy(client, issue, monkeypatch):
    from pydantic import SecretStr

    from backend.services.diagnosis import diagnose

    case = EvaluationCase(
        id="service_failure",
        group="Wi-Fi",
        input=issue,
        expected_category="Network / Wi-Fi",
        expected_article="KB-001",
        expected_escalation=False,
    )
    with client.app.state.sessions() as session:
        fallback = diagnose(session, client.app.state.settings, case.input)
        monkeypatch.setattr("evaluation.run.diagnose", lambda *args: fallback)
        client.app.state.settings.openai_api_key = SecretStr("mock-only")
        result = evaluate(session, client.app.state.settings, [case], mode="live", allow_paid=True)
    assert result["service_successes"] == 0
    assert result["classification_accuracy"] == 0
    assert result["escalation_accuracy"] == 0
    assert result["cases"][0]["predicted_category"] is None
