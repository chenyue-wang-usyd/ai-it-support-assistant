from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.parametrize(
    "description,hours",
    [
        ("The laptop battery is swollen and burning.", 4),
        ("My laptop cannot connect to Wi-Fi at my desk.", 24),
        ("The application has a minor issue with a workaround available.", 72),
    ],
)
def test_sla_budgets(client, description, hours):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    client.app.state.clock = lambda: start
    ticket = client.post(
        "/tickets", json={"title": "Reported fault", "description": description}
    ).json()
    sla = client.get(f"/tickets/{ticket['id']}/sla").json()
    assert datetime.fromisoformat(sla["due_at"]) == start + timedelta(hours=hours)
    assert sla["remaining_seconds"] == hours * 3600
    assert sla["state"] == "On Track"


@pytest.mark.parametrize(
    "elapsed,state,breached",
    [
        (21, "On Track", False),
        (22, "Due Soon", False),
        (24, "Due Soon", False),
        (24.000001, "Breached", True),
    ],
)
def test_sla_deadline_boundaries(client, issue, elapsed, state, breached):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    client.app.state.clock = lambda: start
    ticket = client.post("/tickets", json=issue).json()
    client.app.state.clock = lambda: start + timedelta(hours=elapsed)
    result = client.get(f"/tickets/{ticket['id']}/sla").json()
    assert result["state"] == state
    assert result["breached"] is breached
    stats = client.get("/stats").json()
    assert stats["sla_breaches"] == int(breached)
    assert stats["sla_due_soon"] == int(state == "Due Soon")
    rows = client.get("/sla/tickets", params={"state": state}).json()
    assert len(rows) == 1 and rows[0]["ticket_id"] == ticket["id"]


def test_resolution_freezes_clock_and_reopen_retains_deadline(client, issue):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    client.app.state.clock = lambda: start
    ticket = client.post("/tickets", json=issue).json()
    path = f"/tickets/{ticket['id']}"
    client.app.state.clock = lambda: start + timedelta(hours=6)
    client.patch(path, json={"status": "Resolved"})
    client.app.state.clock = lambda: start + timedelta(hours=30)
    before = client.get(path + "/sla").json()
    assert before["state"] == "Resolved" and before["elapsed_hours"] == 6
    client.post(path + "/notes", json={"note": "Review after resolution."})
    client.patch(path, json={"status": "Resolved"})
    assert client.get(path + "/sla").json()["resolved_at"] == before["resolved_at"]
    stats = client.get("/stats").json()
    assert stats["average_resolution_hours"] == pytest.approx(6, abs=0.0001)
    assert stats["measured_resolutions"] == 1
    client.patch(path, json={"status": "Open"})
    reopened = client.get(path + "/sla").json()
    assert reopened["due_at"] == before["due_at"]
    assert reopened["state"] == "Breached" and reopened["resolved_at"] is None
    assert client.get("/stats").json()["average_resolution_hours"] is None
    client.patch(path, json={"status": "Resolved"})
    stats = client.get("/stats").json()
    assert stats["resolved_sla_breaches"] == 1
    assert stats["average_resolution_hours"] == pytest.approx(30, abs=0.0001)


def test_duplicate_detection_is_advisory_and_excludes_resolved(client, issue):
    original = client.post("/tickets", json=issue).json()
    matches = client.post("/tickets/duplicates", json=issue).json()
    assert matches[0]["ticket_id"] == original["id"]
    assert matches[0]["similarity"] == 1
    assert len(matches[0]["shared_terms"]) >= 2
    response = client.post("/tickets", json=issue)
    assert response.status_code == 201
    assert response.headers["X-Possible-Duplicate-Count"] == "1"
    assert client.get("/stats").json()["total_tickets"] == 2
    for ticket in client.get("/tickets").json():
        client.patch(f"/tickets/{ticket['id']}", json={"status": "Resolved"})
    assert client.post("/tickets/duplicates", json=issue).json() == []


def test_duplicate_threshold_is_configurable(client, issue):
    client.post("/tickets", json=issue)
    candidate = {**issue, "description": issue["description"] + " Error adapter unavailable today."}
    client.app.state.settings.duplicate_similarity_threshold = 0.5
    assert client.post("/tickets/duplicates", json=candidate).json()
    client.app.state.settings.duplicate_similarity_threshold = 0.9999
    assert client.post("/tickets/duplicates", json=candidate).json() == []


def test_generic_platform_words_do_not_prove_duplication(client):
    original = {
        "title": "Wi-Fi Windows issue",
        "description": "Wi-Fi Windows network laptop error.",
    }
    client.post("/tickets", json=original)
    client.app.state.settings.duplicate_similarity_threshold = 0.5
    assert client.post("/tickets/duplicates", json=original).json() == []
    other = {
        "title": "Windows printer fault",
        "description": "The paper tray is jammed on printer B.",
    }
    assert client.post("/tickets/duplicates", json=other).json() == []


def test_sla_input_validation_and_unknown_ticket(client):
    from uuid import uuid4

    assert client.get(f"/tickets/{uuid4()}/sla").status_code == 404
    assert client.get("/sla/tickets", params={"state": "Unknown"}).status_code == 422
    assert (
        client.post("/tickets/duplicates", json={"title": "a", "description": "x"}).status_code
        == 422
    )
