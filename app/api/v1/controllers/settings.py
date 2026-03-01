import json
from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from app.api.dependencies import get_db_session
from app.models.setting import Setting
from app.schemas.setting import SettingsIn
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

# llm_providers stored as encrypted JSON string (contains api keys)
SENSITIVE_KEYS = ["groq_key", "openrouter_key", "apollo_key", "llm_providers"]

@router.get("/")
def get_settings(session: Session = Depends(get_db_session)):
    db_rows = session.exec(select(Setting)).all()
    overrides: dict = {}

    for row in db_rows:
        if row.key in SENSITIVE_KEYS:
            overrides[row.key] = row.get_decrypted_value()
        else:
            overrides[row.key] = row.value

    # Parse llm_providers from stored JSON string → list
    raw_providers = overrides.get("llm_providers", "") or ""
    try:
        llm_providers = json.loads(raw_providers) if raw_providers else []
    except Exception:
        llm_providers = []

    return {
        "llm_providers":   llm_providers,
        # Legacy individual keys (returned for backward compat)
        "groq_key":        overrides.get("groq_key", ""),
        "openrouter_key":  overrides.get("openrouter_key", ""),
        "apollo_key":      overrides.get("apollo_key", ""),
        "llm_provider":    overrides.get("llm_provider", "groq"),
        "openrouter_model": overrides.get("openrouter_model", ""),
        "send_strategy":   overrides.get("send_strategy", "round_robin"),
        "batch_size":      int(overrides.get("batch_size", 5)),
        "custom_email_template": overrides.get("custom_email_template", ""),
        "email_style_instructions": overrides.get("email_style_instructions", ""),
        "sample_email_copy":     overrides.get("sample_email_copy", ""),
        "calendar_url":    overrides.get("calendar_url", ""),
        "sender_name":     overrides.get("sender_name", ""),
        "sender_title":    overrides.get("sender_title", ""),
    }

@router.post("/")
def update_settings(body: SettingsIn, session: Session = Depends(get_db_session)):
    updates = body.model_dump(exclude_unset=True)
    for k, v in updates.items():
        if v is None:
            continue

        # llm_providers arrives as list[dict] — serialise to JSON for storage
        if k == "llm_providers":
            v = json.dumps(v)
        elif k == "batch_size":
            v = str(int(v))
        else:
            v = str(v).strip()

        row = session.exec(select(Setting).where(Setting.key == k)).first()
        if not row:
            row = Setting(key=k)

        if k in SENSITIVE_KEYS:
            row.set_encrypted_value(v)
        else:
            row.value = v

        session.add(row)
    session.commit()
    return {"status": "settings updated"}


class LLMTestIn(BaseModel):
    provider:  str
    api_key:   str
    model:     Optional[str] = ""

@router.post("/test-llm")
async def test_llm_connection(body: LLMTestIn):
    """Quick smoke-test: call the provider with a trivial prompt, return ok/error."""
    from app.utils.llm_client import generate_email, PROVIDER_DEFS

    provider = (body.provider or "").lower().strip()
    api_key  = (body.api_key  or "").strip()
    model    = (body.model    or "").strip()

    if not api_key:
        return {"ok": False, "error": "No API key provided"}
    if provider not in PROVIDER_DEFS:
        return {"ok": False, "error": f"Unknown provider '{provider}'"}

    pdef       = PROVIDER_DEFS[provider]
    model_used = model or pdef["default_model"]

    # Minimal prompt — just check the key is valid and the model responds
    test_sys  = "You are a helpful assistant. Reply only with valid JSON."
    test_user = 'Reply with exactly this JSON and nothing else: {"subject": "OK", "bodyHtml": "<p>OK</p>"}'

    try:
        result = await generate_email(
            test_sys, test_user,
            providers=[{"provider": provider, "api_key": api_key, "model": model_used}],
        )
        return {"ok": True, "model_used": model_used, "subject": result.get("subject", "")}
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}
