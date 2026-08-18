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


def _ensure_columns() -> None:
    """Add new columns to an existing DB without dropping data. Guarded ALTER TABLE — a
    minimal migration for the additive column case; a real column change would want Alembic."""
    wanted = {"freshness": "freshness TEXT DEFAULT 'ACTIVE'"}
    with ENGINE.begin() as conn:
        have = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(jobs)")}
        for col, ddl in wanted.items():
            if col not in have:
                conn.exec_driver_sql(f"ALTER TABLE jobs ADD COLUMN {ddl}")


def init_db() -> None:
    # create_all is additive for whole tables; _ensure_columns handles new columns.
    Base.metadata.create_all(ENGINE)
    _ensure_columns()
    with SessionLocal() as s:
        row = s.get(SchemaMeta, "schema_version")
        if row is None:
            s.add(SchemaMeta(key="schema_version", value=str(SCHEMA_VERSION)))
        else:
            row.value = str(SCHEMA_VERSION)
        s.commit()


def get_session() -> Session:
    return SessionLocal()
