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
    import secrets

    # ── Lead columns ─────────────────────────────────────────────────────────
    lead_columns = [
        ("headline",           "TEXT NOT NULL DEFAULT ''"),
        ("twitter",            "TEXT NOT NULL DEFAULT ''"),
        ("phone",              "TEXT NOT NULL DEFAULT ''"),
        ("departments",        "TEXT NOT NULL DEFAULT ''"),
        ("org_industry",       "TEXT NOT NULL DEFAULT ''"),
        ("org_founded",        "TEXT NOT NULL DEFAULT ''"),
        ("org_description",    "TEXT NOT NULL DEFAULT ''"),
        ("org_funding",        "TEXT NOT NULL DEFAULT ''"),
        ("org_tech_stack",     "TEXT NOT NULL DEFAULT ''"),
        ("draft_subject",      "TEXT NOT NULL DEFAULT ''"),
        ("draft_body",         "TEXT NOT NULL DEFAULT ''"),
        ("unsubscribe_token",  "TEXT NOT NULL DEFAULT ''"),
        ("is_unsubscribed",    "INTEGER NOT NULL DEFAULT 0"),
        ("lead_score",         "INTEGER NOT NULL DEFAULT 0"),
    ]

    # ── Campaign columns ──────────────────────────────────────────────────────
    campaign_columns = [
        ("tracking_id",    "TEXT NOT NULL DEFAULT ''"),
        ("opened_at",      "TEXT"),
        ("open_count",     "INTEGER NOT NULL DEFAULT 0"),
        ("sequence_step",  "INTEGER NOT NULL DEFAULT 0"),
    ]

    with sqlite3.connect(_DB_PATH) as con:
        # Lead migrations
        cur = con.execute("PRAGMA table_info(lead)")
        existing_lead = {row[1] for row in cur.fetchall()}
        for col_name, col_def in lead_columns:
            if col_name not in existing_lead:
                con.execute(f"ALTER TABLE lead ADD COLUMN {col_name} {col_def}")

        # Back-fill unsubscribe_token for any existing leads that have none
        con.execute(
            "SELECT id FROM lead WHERE unsubscribe_token = '' OR unsubscribe_token IS NULL"
        )
        for (lid,) in con.execute(
            "SELECT id FROM lead WHERE unsubscribe_token = '' OR unsubscribe_token IS NULL"
        ).fetchall():
            con.execute(
                "UPDATE lead SET unsubscribe_token = ? WHERE id = ?",
                (secrets.token_hex(16), lid),
            )

        # Campaign migrations
        cur = con.execute("PRAGMA table_info(campaign)")
        existing_campaign = {row[1] for row in cur.fetchall()}
        for col_name, col_def in campaign_columns:
            if col_name not in existing_campaign:
                con.execute(f"ALTER TABLE campaign ADD COLUMN {col_name} {col_def}")

        # Back-fill tracking_id for existing campaigns
        for (cid,) in con.execute(
            "SELECT id FROM campaign WHERE tracking_id = '' OR tracking_id IS NULL"
        ).fetchall():
            con.execute(
                "UPDATE campaign SET tracking_id = ? WHERE id = ?",
                (secrets.token_hex(16), cid),
            )

        con.commit()
