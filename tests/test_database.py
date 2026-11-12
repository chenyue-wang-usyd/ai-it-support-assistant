import pytest
from sqlalchemy.exc import OperationalError

from backend.database import build_engine
from backend.services.knowledge import search_articles


def test_empty_knowledge_base_returns_no_matches(client):
    from backend.models import KnowledgeBaseArticle

    with client.app.state.sessions() as session:
        session.query(KnowledgeBaseArticle).delete()
        session.commit()
        assert search_articles(session, "Wi-Fi") == []


def test_non_sqlite_url_is_rejected():
    with pytest.raises(ValueError, match="SQLite only"):
        build_engine("postgresql://localhost/demo")


def test_database_error_is_sanitized(client, monkeypatch):
    from sqlalchemy.orm import Session

    def unavailable(*args, **kwargs):
        raise OperationalError("PRIVATE SQL", {}, Exception("PRIVATE DETAILS"))

    monkeypatch.setattr(Session, "execute", unavailable)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database temporarily unavailable."}
    assert "PRIVATE" not in response.text
