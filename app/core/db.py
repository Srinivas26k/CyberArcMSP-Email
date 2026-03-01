"""
database.py — SQLite engine, session factory, and DB initialization

The database file is stored in the OS user-data directory so it persists
across application upgrades:
  • Windows: %APPDATA%\\CyberArc Outreach\\database.db
  • macOS:   ~/Library/Application Support/CyberArc Outreach/database.db
  • Linux:   ~/.local/share/CyberArc Outreach/database.db

The path can be overridden by setting the APP_DATA_DIR environment variable
(Electron sets this automatically so the Python server knows where to look).
"""
import os
from sqlmodel import SQLModel, create_engine
from app.core.vault import VaultManager


def _resolve_db_path() -> str:
    """
    Return the absolute path to database.db, honouring APP_DATA_DIR if set.
    """
    app_data_dir = os.environ.get("APP_DATA_DIR", "").strip()
    if app_data_dir:
        os.makedirs(app_data_dir, exist_ok=True)
        return os.path.join(app_data_dir, "database.db")

    # Dev / fallback: place next to this file
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")


_DB_PATH = _resolve_db_path()

# Revert to standard SQLite, we will rely on VaultManager for Application-Layer AES encryption
# to bypass the C-binary compilation issues of SQLCipher on random environments.
DATABASE_URL = f"sqlite:///{_DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},  # needed for SQLite + FastAPI
)


def init_db():
    """Create all tables. Called once on startup."""
    import app.models  # noqa: F401
    
    # Pre-heat the Vault engine so key generation occurs safely on boot
    VaultManager._initialize()

    SQLModel.metadata.create_all(engine)
    _migrate_db()


def _migrate_db():
    """
    Non-destructive schema migration — adds any new columns that don't yet
    exist in the SQLite database.  Safe to run on every startup.
    """
    import sqlite3

    new_columns = [
        ("headline",        "TEXT NOT NULL DEFAULT ''"),
        ("twitter",         "TEXT NOT NULL DEFAULT ''"),
        ("phone",           "TEXT NOT NULL DEFAULT ''"),
        ("departments",     "TEXT NOT NULL DEFAULT ''"),
        ("org_industry",    "TEXT NOT NULL DEFAULT ''"),
        ("org_founded",     "TEXT NOT NULL DEFAULT ''"),
        ("org_description", "TEXT NOT NULL DEFAULT ''"),
        ("org_funding",     "TEXT NOT NULL DEFAULT ''"),
        ("org_tech_stack",  "TEXT NOT NULL DEFAULT ''"),
        ("draft_subject",   "TEXT NOT NULL DEFAULT ''"),
        ("draft_body",      "TEXT NOT NULL DEFAULT ''"),
    ]

    with sqlite3.connect(_DB_PATH) as con:
        cur = con.execute("PRAGMA table_info(lead)")
        existing = {row[1] for row in cur.fetchall()}
        for col_name, col_def in new_columns:
            if col_name not in existing:
                con.execute(f"ALTER TABLE lead ADD COLUMN {col_name} {col_def}")
        con.commit()
