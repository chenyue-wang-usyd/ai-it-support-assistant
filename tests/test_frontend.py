from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture
def ui(client, monkeypatch):
    # Exercise the real Streamlit code against an isolated FastAPI/SQLite test app.
    def request(method, url, **kwargs):
        kwargs.pop("timeout", None)
        return client.request(method, httpx.URL(url).raw_path.decode(), **kwargs)

    monkeypatch.setattr(httpx, "request", request)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    app = AppTest.from_file(str(Path(__file__).parents[1] / "frontend/app.py"))
    app.run(timeout=20)
    assert not app.exception
    return app


def button(ui, label):
    return next(item for item in ui.button if item.label == label)


def test_ui_ticket_journey(ui, client):
    assert ui.metric[0].value == "0"
    ui.radio[0].set_value("AI Troubleshooting").run()
    ui.text_input[0].set_value("Laptop Wi-Fi issue")
    ui.text_area[0].set_value("My laptop cannot connect to Wi-Fi, but other devices work normally.")
    button(ui, "Analyze issue").click().run()
    assert not ui.exception
    assert any(item.value == "Rule-based Demo Mode" for item in ui.info)
    button(ui, "Create ticket").click().run()
    assert not ui.exception
    assert client.get("/stats").json()["total_tickets"] == 1
    assert button(ui, "Create ticket").disabled
    ui.radio[0].set_value("Ticket Management").run()
    assert not ui.exception
    next(item for item in ui.selectbox if item.label == "Ticket status").set_value("Resolved")
    button(ui, "Save status").click().run()
    assert not ui.exception
    assert client.get("/stats").json()["by_status"]["Resolved"] == 1
    ui.radio[0].set_value("Dashboard").run()
    assert ui.metric[0].value == "1"
    assert ui.metric[3].value == "1"
    assert not ui.exception


def test_ui_knowledge_search_and_input_errors(ui):
    ui.radio[0].set_value("Knowledge Base").run()
    ui.text_input[0].set_value("Wi-Fi")
    button(ui, "Search").click().run()
    assert not ui.exception
    assert any("KB-001" in item.label for item in ui.expander)
    ui.radio[0].set_value("AI Troubleshooting").run()
    button(ui, "Analyze issue").click().run()
    assert ui.error
    assert not ui.exception


def test_backend_unavailable_is_visible(monkeypatch):
    def offline(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "request", offline)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "frontend/app.py")).run()
    assert app.error
    assert not app.exception


def analyze_wifi(ui):
    ui.radio[0].set_value("AI Troubleshooting").run()
    next(item for item in ui.text_input if item.label == "Issue title").set_value(
        "Laptop Wi-Fi issue"
    )
    next(item for item in ui.text_area if item.label == "What happened?").set_value(
        "My laptop cannot connect to Wi-Fi, but other devices work normally."
    )
    button(ui, "Analyze issue").click().run()


def test_feedback_followup_and_explicit_ticket_actions(ui, client):
    analyze_wifi(ui)
    button(ui, "Problem Solved").click().run()
    assert client.get("/stats").json()["total_tickets"] == 0
    preview_id = ui.session_state["preview"]["result"]["diagnosis_id"]
    assert client.get(f"/diagnose/{preview_id}/feedback").json()[0]["outcome"] == "solved"
    button(ui, "Still Having Issues").click().run()
    next(item for item in ui.text_area if item.label == "Additional observations").set_value(
        "The error message says wireless adapter unavailable."
    )
    button(ui, "Analyze additional details").click().run()
    assert not ui.exception
    assert ui.session_state["preview"]["result"]["diagnosis_id"] != preview_id
    assert client.get("/stats").json()["total_tickets"] == 0
    button(ui, "Create ticket").click().run()
    ticket = client.get("/tickets").json()[0]
    button(ui, "Update linked ticket diagnosis").click().run()
    assert not ui.exception
    assert client.get(f"/tickets/{ticket['id']}").json()["status"] == "Open"
    button(ui, "Problem Solved").click().run()
    assert client.get(f"/tickets/{ticket['id']}").json()["status"] == "Open"
    button(ui, "Mark linked ticket Resolved").click().run()
    assert client.get(f"/tickets/{ticket['id']}").json()["status"] == "Resolved"
    ui.radio[0].set_value("Ticket Management").run()
    next(item for item in ui.text_area if item.label == "Support note").set_value(
        "Verified with the user."
    )
    button(ui, "Add support note").click().run()
    assert not ui.exception
    assert (
        client.get(f"/tickets/{ticket['id']}/events").json()[-1]["note"]
        == "Verified with the user."
    )
    next(item for item in ui.selectbox if item.label == "Ticket status").set_value("Open")
    button(ui, "Save status").click().run()
    assert (
        client.get(f"/tickets/{ticket['id']}/events").json()[-1]["event_type"] == "Ticket Reopened"
    )


def test_duplicate_button_opens_and_retains_correct_ticket(ui, client, issue):
    first = client.post("/tickets", json=issue).json()
    client.post(
        "/tickets",
        json={
            **issue,
            "title": "A different problem",
            "description": "My printer has a paper jam.",
        },
    )
    analyze_wifi(ui)
    button(ui, "Open existing ticket " + first["id"][:8]).click().run()
    assert not ui.exception
    assert ui.radio[0].value == "Ticket Management"
    assert next(item for item in ui.selectbox if item.label == "Open ticket").value == first["id"]
    button(ui, "Refresh ticket").click().run()
    assert next(item for item in ui.selectbox if item.label == "Open ticket").value == first["id"]
    next(item for item in ui.selectbox if item.label == "Filter by category").set_value(
        "Email"
    ).run()
    assert not ui.exception
    assert next(item for item in ui.selectbox if item.label == "Open ticket").value == first["id"]
