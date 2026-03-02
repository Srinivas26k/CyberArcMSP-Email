"""
sequence.py — Multi-step follow-up sequence models.

A SequenceTemplate defines the follow-up steps (what to send and when).
A SequenceEnrollment tracks a lead's progress through a sequence.

Step schema (steps_json is a JSON array of these):
  {
    "delay_days": 3,           # days after previous step (or enrollment for step 0)
    "subject_hint": "Re:",     # optional subject prefix/hint
    "instructions": "..."      # free-text guidance for AI (tone, angle, length)
  }
"""
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field
from app.models.base import Base


class SequenceTemplate(Base, table=True):
    """A reusable multi-step email follow-up sequence definition."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(default="")
    description: str = Field(default="")
    # JSON array of step objects: [{delay_days, subject_hint, instructions}, ...]
    steps_json: str = Field(default="[]")
    is_active: bool = Field(default=True)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class SequenceEnrollment(Base, table=True):
    """Tracks a lead's progress through a follow-up sequence."""
    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="lead.id", index=True)
    sequence_id: int = Field(foreign_key="sequencetemplate.id", index=True)
    current_step: int = Field(default=0)   # index of next step to send
    status: str = Field(default="active")  # active | completed | stopped | replied
    enrolled_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    next_send_at: Optional[str] = None     # ISO datetime for next send
    last_sent_at: Optional[str] = None
    initial_subject: str = Field(default="")  # subject of step-0 email (for threading)
