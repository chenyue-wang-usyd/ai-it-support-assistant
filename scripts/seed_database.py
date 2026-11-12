"""Run from the repository root: python -m scripts.seed_database."""

from backend.config import Settings
from backend.database import Base, build_engine, session_factory
from backend.services.knowledge import seed_knowledge_base


def main():
    engine = build_engine(Settings().database_url)
    Base.metadata.create_all(engine)
    with session_factory(engine)() as session:
        seed_knowledge_base(session)
    engine.dispose()
    print("Knowledge base initialized. Existing article IDs were preserved.")


if __name__ == "__main__":
    main()
