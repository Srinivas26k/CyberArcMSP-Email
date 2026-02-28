from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from app.api.dependencies import get_db_session
from app.models.setting import Setting
from app.schemas.setting import SettingsIn

router = APIRouter()

SENSITIVE_KEYS = ["groq_key", "openrouter_key", "apollo_key"]

@router.get("/")
def get_settings(session: Session = Depends(get_db_session)):
    db_rows = session.exec(select(Setting)).all()
    overrides = {}
    
    for row in db_rows:
        if row.key in SENSITIVE_KEYS:
            overrides[row.key] = row.get_decrypted_value()
        else:
            overrides[row.key] = row.value
    
    # We remove old settings.groq_api_key os.env fallbacks here. 
    # Must be set by user in DB explicitly.
    return {
        "groq_key": overrides.get("groq_key", ""),
        "openrouter_key": overrides.get("openrouter_key", ""),
        "apollo_key": overrides.get("apollo_key", ""),
        "llm_provider": overrides.get("llm_provider", "groq"),
        "openrouter_model": overrides.get("openrouter_model", ""),
        "send_strategy": overrides.get("send_strategy", "round_robin"),
        "batch_size": int(overrides.get("batch_size", 5)),
        # Legacy fields to avoid breaking old UI immediately until Identity profile replaces them
        "calendar_url": overrides.get("calendar_url", ""),
        "sender_name": overrides.get("sender_name", ""),
        "sender_title": overrides.get("sender_title", ""),
    }

@router.post("/")
def update_settings(body: SettingsIn, session: Session = Depends(get_db_session)):
    updates = body.model_dump(exclude_unset=True)
    for k, v in updates.items():
        if v is None:
            continue
            
        row = session.exec(select(Setting).where(Setting.key == k)).first()
        if not row:
            row = Setting(key=k)
            
        if k in SENSITIVE_KEYS:
            row.set_encrypted_value(str(v).strip())
        else:
            row.value = str(v).strip()
            
        session.add(row)
    session.commit()
    return {"status": "settings updated, sensitive keys encrypted in vault"}
