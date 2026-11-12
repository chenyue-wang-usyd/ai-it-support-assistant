import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from backend.config import Settings
from backend.database import build_engine, session_factory
from backend.models import utc_now
from backend.routes.api import router
from backend.services.knowledge import seed_knowledge_base
from backend.services.migrations import upgrade_database


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    engine = build_engine(settings.database_url)
    sessions = session_factory(engine)

    @asynccontextmanager
    async def lifespan(app):
        upgrade_database(engine, sessions)
        with sessions() as session:
            seed_knowledge_base(session)
        yield
        engine.dispose()

    app = FastAPI(
        title="AI IT Support Assistant",
        version="2.0.0",
        lifespan=lifespan,
        description="Local portfolio helpdesk. No authentication; bind to loopback only.",
    )
    app.state.settings = settings
    app.state.sessions = sessions
    app.state.clock = utc_now
    app.include_router(router)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logging.getLogger(__name__).error("Database operation failed.")
        return JSONResponse(
            status_code=503, content={"detail": "Database temporarily unavailable."}
        )

    return app


app = create_app()
