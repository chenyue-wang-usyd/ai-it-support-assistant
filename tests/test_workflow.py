from uuid import uuid4

import pytest


def test_feedback_and_followup_do_not_change_tickets(client, issue):
    ticket = client.post("/tickets", json=issue).json()
    preview = client.post("/diagnose", json=issue).json()
    assert preview["clarifying_questions"]
    feedback = client.post(
        f"/diagnose/{preview['diagnosis_id']}/feedback",
        json={"outcome": "solved", "ticket_id": ticket["id"]},
    )
    assert feedback.status_code == 201
    assert feedback.json()["created_at"].endswith("Z")
    assert client.get(f"/tickets/{ticket['id']}").json()["status"] == "Open"
    history = client.get(f"/diagnose/{preview['diagnosis_id']}/feedback").json()
    assert len(history) == 1 and history[0]["outcome"] == "solved"
    followup = client.post(
        f"/diagnose/{preview['diagnosis_id']}/follow-up",
        json={"details": "The error message says wireless adapter unavailable."},
    )
    assert followup.status_code == 200
    new = followup.json()
    assert new["diagnosis_id"] != preview["diagnosis_id"]
    assert new["mode"] == "Rule-based Demo Mode"
    assert client.get("/stats").json()["total_tickets"] == 1
    applied = client.post(
        f"/tickets/{ticket['id']}/diagnosis", json={"diagnosis_id": new["diagnosis_id"]}
    )
    assert applied.status_code == 200
    assert applied.json()["status"] == "Open"
    assert applied.json()["description"] == issue["description"]
    assert applied.json()["diagnosis"]["analysis"] == new["analysis"]


def test_timeline_notes_resolve_reopen_and_noop(client, issue):
    ticket = client.post("/tickets", json=issue).json()
    path = f"/tickets/{ticket['id']}"
    events = client.get(path + "/events").json()
    assert [e["event_type"] for e in events] == ["Ticket Created", "Rule-based Diagnosis Generated"]
    for status in ["In Progress", "Resolved", "Open", "Open"]:
        assert client.patch(path, json={"status": status}).status_code == 200
    note = client.post(
        path + "/notes", json={"note": "User confirmed a recurrence after reconnecting."}
    )
    assert note.status_code == 201
    events = client.get(path + "/events").json()
    assert [e["event_type"] for e in events][2:] == [
        "Status Changed",
        "Ticket Resolved",
        "Ticket Reopened",
        "Support Note Added",
    ]
    assert events[4]["previous_value"] == "Resolved"
    assert events[4]["new_value"] == "Open"
    assert events[-1]["note"].startswith("User confirmed")
    assert all(e["timestamp"].endswith("Z") for e in events)
    assert [e["timestamp"] for e in events] == sorted(e["timestamp"] for e in events)


@pytest.mark.parametrize(
    "suffix,body",
    [
        ("feedback", {"outcome": "unknown"}),
        ("feedback", {"outcome": "solved", "note": " "}),
        ("follow-up", {"details": "short"}),
    ],
)
def test_bad_feedback_input(client, suffix, body):
    assert client.post(f"/diagnose/{uuid4()}/{suffix}", json=body).status_code == 422


def test_missing_resources_and_mismatched_diagnosis(client, issue):
    missing = str(uuid4())
    assert client.get(f"/tickets/{missing}/events").status_code == 404
    assert (
        client.post(f"/tickets/{missing}/notes", json={"note": "Investigation"}).status_code == 404
    )
    assert client.get(f"/diagnose/{missing}/feedback").status_code == 404
    assert (
        client.post(f"/diagnose/{missing}/feedback", json={"outcome": "solved"}).status_code == 404
    )
    assert (
        client.post(
            f"/diagnose/{missing}/follow-up",
            json={"details": "A new observation with enough detail."},
        ).status_code
        == 404
    )
    ticket = client.post("/tickets", json=issue).json()
    other = client.post("/diagnose", json={**issue, "title": "Unrelated issue"}).json()
    assert (
        client.post(
            f"/tickets/{ticket['id']}/diagnosis", json={"diagnosis_id": other["diagnosis_id"]}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/diagnose/{other['diagnosis_id']}/feedback",
            json={"outcome": "solved", "ticket_id": missing},
        ).status_code
        == 404
    )


def test_followup_length_limit(client, issue):
    preview = client.post("/diagnose", json={**issue, "description": "x" * 5990}).json()
    response = client.post(
        f"/diagnose/{preview['diagnosis_id']}/follow-up",
        json={"details": "An additional observation."},
    )
    assert response.status_code == 422
    assert client.get("/stats").json()["total_tickets"] == 0
