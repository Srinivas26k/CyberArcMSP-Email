"""
models.py — SQLModel table definitions for SRV AI Email Outreach
"""
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field, SQLModel


class EmailAccount(SQLModel, table=True):
    """A connected sender email account (Gmail or Outlook)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    app_password: str
    provider: str = Field(description="'gmail' or 'outlook'")
    display_name: str = Field(default="")
    is_active: bool = Field(default=True)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Lead(SQLModel, table=True):
    """A prospective contact imported via CSV or Apollo.io."""
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    first_name: str = Field(default="")
    last_name: str = Field(default="")
    company: str = Field(default="")
    role: str = Field(default="")
    industry: str = Field(default="Technology")
    location: str = Field(default="")
    seniority: str = Field(default="")
    employees: str = Field(default="")
    website: str = Field(default="")
    linkedin: str = Field(default="")
    # Lifecycle: pending → drafting → sent → replied | failed
    status: str = Field(default="pending", index=True)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Campaign(SQLModel, table=True):
    """A single email send event linking a lead to an account."""
    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="lead.id", index=True)
    account_id: Optional[int] = Field(default=None, foreign_key="emailaccount.id")
    subject: str = Field(default="")
    sent_at: Optional[str] = None
    error_message: Optional[str] = None
    thread_id: Optional[str] = None


class Reply(SQLModel, table=True):
    """An inbound reply detected via IMAP."""
    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id")
    from_email: str = Field(default="")
    from_name: str = Field(default="")
    subject: str = Field(default="")
    snippet: str = Field(default="")
    inbox_account: str = Field(default="")
    received_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Setting(SQLModel, table=True):
    """Key-value store for runtime configuration."""
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    value: str = Field(default="")
