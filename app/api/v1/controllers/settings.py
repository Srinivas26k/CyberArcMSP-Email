import os
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from app.api.dependencies import get_db_session
from app.models.setting import Setting
from app.schemas.setting import SettingsIn
from app.core.config import settings

router = APIRouter()

@router.get("/")
def get_settings(session: Session = Depends(get_db_session)):
    db_rows = session.exec(select(Setting)).all()
    overrides = {row.key: row.value for row in db_rows}
    
    # Merge env logic
    return {
        "groq_key": overrides.get("groq_key", settings.groq_api_key),
        "openrouter_key": overrides.get("openrouter_key", settings.openrouter_api_key),
        "apollo_key": overrides.get("apollo_key", settings.apollo_api_key),
        "calendar_url": overrides.get("calendar_url", settings.calendly_url),
        "sender_name": overrides.get("sender_name", settings.sender_name),
        "sender_title": overrides.get("sender_title", settings.sender_title),
        "llm_provider": overrides.get("llm_provider", settings.llm_provider),
        "openrouter_model": overrides.get("openrouter_model", settings.openrouter_model),
        "send_strategy": overrides.get("send_strategy", "round_robin"),
        "batch_size": int(overrides.get("batch_size", 5))
    }

@router.post("/")
def update_settings(body: SettingsIn, session: Session = Depends(get_db_session)):
    updates = body.model_dump(exclude_unset=True)
    for k, v in updates.items():
        if v is None:
            continue
        row = session.exec(select(Setting).where(Setting.key == k)).first()
        if not row:
            row = Setting(key=k, value=str(v).strip())
        else:
            row.value = str(v).strip()
        session.add(row)
    session.commit()
    return {"status": "settings updated"}
