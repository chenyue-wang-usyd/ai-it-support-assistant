import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app


@pytest.fixture(autouse=True)
def no_paid_calls(monkeypatch):
    # Any unmocked SDK call fails immediately, even if the host has an API key.
    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must never call the real OpenAI API.")

    monkeypatch.setattr("backend.services.diagnosis.OpenAI", forbidden)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None, database_url=f"sqlite:///{tmp_path / 'test.db'}", openai_api_key=""
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def issue():
    return {
        "title": "Laptop Wi-Fi issue",
        "description": "My laptop cannot connect to Wi-Fi, but other devices work normally.",
        "category": None,
    }
