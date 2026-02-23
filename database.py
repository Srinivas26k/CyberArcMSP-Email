"""
database.py — SQLite engine, session factory, and DB initialization
"""
import os
from sqlmodel import SQLModel, create_engine, Session

# Place database in project root
_DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")
DATABASE_URL = f"sqlite:///{_DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},  # needed for SQLite + FastAPI
)


def init_db():
    """Create all tables. Called once on startup."""
    # Import models so SQLModel.metadata is populated
    import models  # noqa: F401 — side-effect import
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency — yields a DB session and closes it after the request."""
    with Session(engine) as session:
        yield session
