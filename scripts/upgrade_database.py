"""Back up SQLite using its online backup API, then apply the idempotent additive upgrade."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from backend.config import Settings
from backend.database import build_engine, session_factory
from backend.services.migrations import upgrade_database


def main():
    engine = build_engine(Settings().database_url)
    source_path = Path(engine.url.database)
    if source_path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = source_path.parent / "backups" / f"before-v2-{stamp}.db"
        backup.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(source_path) as source, sqlite3.connect(backup) as target:
            source.backup(target)
        print(f"Backup created: {backup}")
    upgrade_database(engine, session_factory(engine))
    engine.dispose()
    print("Additive V2 upgrade complete. Existing ticket fields preserved.")


if __name__ == "__main__":
    main()
