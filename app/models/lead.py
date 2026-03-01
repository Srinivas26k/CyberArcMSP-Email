from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field
from app.models.base import Base


class Lead(Base, table=True):
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
    # Extended Apollo fields
    headline: str = Field(default="")
    twitter: str = Field(default="")
    phone: str = Field(default="")
    departments: str = Field(default="")
    org_industry: str = Field(default="")
    org_founded: str = Field(default="")
    org_description: str = Field(default="")
    org_funding: str = Field(default="")
    org_tech_stack: str = Field(default="")
    # Lifecycle: pending -> drafting -> sent -> replied | failed
    status: str = Field(default="pending", index=True)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
