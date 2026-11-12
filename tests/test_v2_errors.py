from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.models import TicketEvent


def test_failed_creation_rolls_back_ticket_sla_and_events(client, issue, monkeypatch):
    def fail(*args):
        raise OperationalError("PRIVATE SQL", {}, Exception("PRIVATE VALUE"))

    monkeypatch.setattr(Session, "commit", fail)
    response = client.post("/tickets", json=issue)
    assert response.status_code == 503
    assert "PRIVATE" not in response.text
    assert client.get("/stats").json()["total_tickets"] == 0
    assert client.get("/sla/tickets").json() == []
    with client.app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(TicketEvent)) == 0


def test_failed_note_rolls_back_event_and_updated_timestamp(client, issue, monkeypatch):
    ticket = client.post("/tickets", json=issue).json()
    path = f"/tickets/{ticket['id']}"
    before = client.get(path + "/events").json()

    def fail(*args):
        raise OperationalError("PRIVATE SQL", {}, Exception("PRIVATE VALUE"))

    monkeypatch.setattr(Session, "commit", fail)
    assert client.post(path + "/notes", json={"note": "This write should fail."}).status_code == 503
    assert client.get(path + "/events").json() == before
    assert client.get(path).json()["updated_at"] == ticket["updated_at"]
