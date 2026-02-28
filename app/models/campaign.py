from typing import Optional
from sqlmodel import Field
from app.models.base import Base


class Campaign(Base, table=True):
    """A single email send event linking a lead to an account."""
    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="lead.id", index=True)
    account_id: Optional[int] = Field(default=None, foreign_key="emailaccount.id")
    subject: str = Field(default="")
    sent_at: Optional[str] = None
    error_message: Optional[str] = None
    thread_id: Optional[str] = None
