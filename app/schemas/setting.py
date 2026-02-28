from typing import Optional
from pydantic import BaseModel

class SettingsIn(BaseModel):
    groq_key:         Optional[str] = None
    openrouter_key:   Optional[str] = None
    apollo_key:       Optional[str] = None
    calendar_url:     Optional[str] = None   # provider-neutral booking link
    sender_name:      Optional[str] = None
    sender_title:     Optional[str] = None
    sender_email:     Optional[str] = None
    llm_provider:     Optional[str] = None   # "groq" | "openrouter"
    openrouter_model: Optional[str] = None
    send_strategy:    Optional[str] = None
    batch_size:       Optional[int] = None
