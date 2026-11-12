from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


def test_create_query_update_and_stats(client, issue):
    response = client.post("/tickets", json=issue)
    assert response.status_code == 201
    ticket = response.json()
    assert ticket["category"] == "Network / Wi-Fi"
    assert ticket["status"] == "Open"
    assert ticket["diagnosis"]["mode"] == "Rule-based Demo Mode"
    assert ticket["created_at"].endswith("Z")
    assert client.get(f"/tickets/{ticket['id']}").json() == ticket
    assert len(client.get("/tickets", params={"status": "Open"}).json()) == 1
    assert client.get("/tickets", params={"category": "Email"}).json() == []
    updated = client.patch(f"/tickets/{ticket['id']}", json={"status": "In Progress"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "In Progress"
    updated = client.patch(f"/tickets/{ticket['id']}", json={"status": "Resolved"})
    assert updated.json()["updated_at"] >= ticket["updated_at"]
    assert client.get("/tickets", params={"status": "Open"}).json() == []
    stats = client.get("/stats").json()
    assert stats["total_tickets"] == 1
    assert stats["by_status"] == {"Open": 0, "In Progress": 0, "Resolved": 1}
    assert stats["by_category"]["Network / Wi-Fi"] == 1
    assert stats["by_priority"][ticket["priority"]] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"title": " "},
        {"description": "short"},
        {"category": "Unknown"},
        {"title": "a" * 161},
        {"description": "a" * 6001},
        {"priority": "High"},
        {"title": None},
        {"diagnosis_id": "not-a-uuid"},
    ],
)
def test_invalid_ticket_input(client, issue, changes):
    assert client.post("/tickets", json={**issue, **changes}).status_code == 422
    assert client.get("/stats").json()["total_tickets"] == 0


def test_not_found_and_invalid_update(client, issue):
    missing = f"/tickets/{uuid4()}"
    assert client.get(missing).status_code == 404
    assert client.patch(missing, json={"status": "Resolved"}).status_code == 404
    assert client.get("/tickets/not-an-id").status_code == 422
    ticket = client.post("/tickets", json=issue).json()
    for update in (
        {"status": "Closed"},
        {},
        {"status": None},
        {"status": "Resolved", "priority": "High"},
    ):
        assert client.patch(f"/tickets/{ticket['id']}", json=update).status_code == 422


def test_filters_pagination_and_empty_stats(client, issue):
    assert client.get("/stats").json()["total_tickets"] == 0
    for _ in range(3):
        client.post("/tickets", json=issue)
    records = client.get("/tickets", params={"priority": "Medium", "limit": 2}).json()
    assert len(records) == 2
    page2 = client.get("/tickets", params={"offset": 2, "limit": 2}).json()
    assert len(page2) == 1
    assert page2[0]["id"] not in {r["id"] for r in records}
    for params in ({"limit": 0}, {"offset": -1}, {"status": "Closed"}):
        assert client.get("/tickets", params=params).status_code == 422


def test_persistence_across_app_restart(settings, issue):
    with TestClient(create_app(settings)) as first:
        ticket = first.post("/tickets", json=issue).json()
        first.patch(f"/tickets/{ticket['id']}", json={"status": "Resolved"})
        diagnosis_id = first.post("/diagnose", json=issue).json()["diagnosis_id"]
    with TestClient(create_app(settings)) as restarted:
        stored = restarted.get(f"/tickets/{ticket['id']}").json()
        assert stored["status"] == "Resolved"
        assert stored["diagnosis"] == ticket["diagnosis"]
        assert restarted.get("/stats").json()["total_tickets"] == 1
        assert len(restarted.get("/knowledge-base").json()) == 18
        assert (
            restarted.post("/tickets", json={**issue, "diagnosis_id": diagnosis_id}).status_code
            == 201
        )


def test_preview_reuse_and_mismatch(client, issue, monkeypatch):
    preview = client.post("/diagnose", json=issue).json()

    def forbidden(*args):
        raise AssertionError("Saving a preview must not repeat diagnosis.")

    monkeypatch.setattr("backend.routes.api.diagnose", forbidden)
    response = client.post("/tickets", json={**issue, "diagnosis_id": preview["diagnosis_id"]})
    assert response.status_code == 201
    assert response.json()["diagnosis"]["analysis"] == preview["analysis"]
    assert (
        client.post(
            "/tickets",
            json={**issue, "title": "Changed title", "diagnosis_id": preview["diagnosis_id"]},
        ).status_code
        == 409
    )
    assert client.post("/tickets", json={**issue, "diagnosis_id": str(uuid4())}).status_code == 404


def test_health_and_search(client):
    assert client.get("/health").json() == {"status": "ok", "ai_configured": False}
    articles = client.get("/knowledge-base").json()
    assert len(articles) == 18
    assert len({a["id"] for a in articles}) == 18
    found = client.get("/knowledge-base", params={"q": "laptop cannot connect Wi-Fi"}).json()
    assert found[0]["id"] == "KB-001"
    assert client.get("/knowledge-base", params={"q": "zzzzqqqqxxxx"}).json() == []
    email = client.get("/knowledge-base", params={"category": "Email"}).json()
    assert len(email) == 3
    assert all(a["category"] == "Email" for a in email)
