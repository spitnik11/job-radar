"""SQLite engine with WAL mode (spec section 15) + schema-version stamping."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from . import SCHEMA_VERSION
from .config import DATA_DIR
from .models import Base, SchemaMeta

DB_PATH = DATA_DIR / "jobs.db"
ENGINE: Engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=ENGINE, expire_on_commit=False)


@event.listens_for(ENGINE, "connect")
def _set_sqlite_pragma(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")     # reliable concurrent reads during ingestion
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


def init_db() -> None:
    # create_all is additive — it adds new tables (job_notes/job_events) without touching
    # existing data. Column-altering changes will need Alembic; new tables don't.
    Base.metadata.create_all(ENGINE)
    with SessionLocal() as s:
        row = s.get(SchemaMeta, "schema_version")
        if row is None:
            s.add(SchemaMeta(key="schema_version", value=str(SCHEMA_VERSION)))
        else:
            row.value = str(SCHEMA_VERSION)
        s.commit()


def get_session() -> Session:
    return SessionLocal()
