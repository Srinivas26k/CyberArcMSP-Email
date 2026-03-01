from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field
from app.models.base import Base


class EmailAccount(Base, table=True):
    """A connected sender email account (Gmail or Outlook)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    app_password: str
    provider: str = Field(description="'gmail' or 'outlook'")
    display_name: str = Field(default="")
    is_active: bool = Field(default=True)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
