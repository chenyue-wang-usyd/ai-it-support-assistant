from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.config import ROOT


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str):
    url = make_url(database_url)
    if url.drivername != "sqlite":
        raise ValueError("This local demo supports SQLite only.")
    if url.database and url.database != ":memory:":
        path = ROOT / url.database
        path.parent.mkdir(parents=True, exist_ok=True)
        url = url.set(database=str(path.resolve()))
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 15})

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")

    return engine


def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session(request: Request):
    with request.app.state.sessions() as session:
        yield session
