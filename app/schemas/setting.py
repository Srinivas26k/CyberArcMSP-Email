from typing import Optional, List
from pydantic import BaseModel

class SettingsIn(BaseModel):
    # Multi-provider LLM slots (up to 5, tried in order)
    llm_providers:    Optional[List[dict]] = None  # [{provider, api_key, model}, ...]
    # Legacy individual keys (kept for backward compat)
    groq_key:         Optional[str] = None
    openrouter_key:   Optional[str] = None
    apollo_key:       Optional[str] = None
    calendar_url:     Optional[str] = None
    sender_name:      Optional[str] = None
    sender_title:     Optional[str] = None
    sender_email:     Optional[str] = None
    llm_provider:          Optional[str] = None
    openrouter_model:      Optional[str] = None
    send_strategy:         Optional[str] = None
    batch_size:            Optional[int] = None
    custom_email_template: Optional[str] = None   # full HTML with {{PLACEHOLDER}} tokens
