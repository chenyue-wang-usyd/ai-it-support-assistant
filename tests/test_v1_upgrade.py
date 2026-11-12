import json
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.main import create_app
from tests.test_ai import valid_analysis


def test_additive_upgrade_preserves_v1_rows_and_is_repeatable(settings):
    """Build a genuine V1-layout table without using the V2 ORM or migration code."""
    database = settings.database_url.removeprefix("sqlite:///")
    diagnosis = {
        "mode": "Rule-based Demo Mode",
        "analysis": valid_analysis(),
        "recommended_articles": [],
        "notice": "V1 saved result",
    }
    ticket_id = str(uuid4())
    with sqlite3.connect(database) as connection:
        connection.execute("""CREATE TABLE tickets (
            id VARCHAR(36) PRIMARY KEY, title VARCHAR(160) NOT NULL,
            description TEXT NOT NULL, category VARCHAR(30) NOT NULL,
            priority VARCHAR(10) NOT NULL, status VARCHAR(20) NOT NULL,
            diagnosis JSON NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)""")
        connection.execute(
            "INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?)",
            (
                ticket_id,
                "Legacy Wi-Fi fault",
                "Original report preserved exactly.",
                "Network / Wi-Fi",
                "Medium",
                "Resolved",
                json.dumps(diagnosis),
                "2026-01-01 00:00:00.000000",
                "2026-01-01 05:00:00.000000",
            ),
        )
        original = connection.execute("SELECT * FROM tickets").fetchall()
    for _ in range(2):
        with TestClient(create_app(settings)) as client:
            ticket = client.get(f"/tickets/{ticket_id}").json()
            assert ticket["status"] == "Resolved"
            events = client.get(f"/tickets/{ticket_id}/events").json()
            assert len(events) == 1
            assert events[0]["event_type"] == "Legacy Ticket Imported"
            assert client.get(f"/tickets/{ticket_id}/sla").json()["resolution_estimated"] is True
            stats = client.get("/stats").json()
            assert stats["estimated_resolutions"] == 1
            assert stats["average_resolution_hours"] is None
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT * FROM tickets").fetchall() == original
        assert len(connection.execute("PRAGMA table_info(tickets)").fetchall()) == 9
    with TestClient(create_app(settings)) as client:
        assert client.patch(f"/tickets/{ticket_id}", json={"status": "Open"}).status_code == 200
        assert (
            client.get(f"/tickets/{ticket_id}/events").json()[-1]["event_type"] == "Ticket Reopened"
        )
