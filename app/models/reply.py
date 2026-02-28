from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field
from app.models.base import Base


class Reply(Base, table=True):
    """An inbound reply detected via IMAP."""
    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id")
    from_email: str = Field(default="")
    from_name: str = Field(default="")
    subject: str = Field(default="")
    snippet: str = Field(default="")
    inbox_account: str = Field(default="")
    received_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
