import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from app.api.dependencies import get_db_session
from app.schemas.campaign import CampaignRequest, DraftRequest
from app.services.campaign_service import campaign_service
from app.core.sse import broadcast
from app.core.state import campaign_state
from app.repositories.lead_repository import lead_repository
from app.repositories.account_repository import account_repository
from app.models.setting import Setting
from app.core.config import settings

router = APIRouter()

@router.post("/start")
async def start_campaign(req: CampaignRequest, session: Session = Depends(get_db_session)):
    global campaign_state
    if campaign_state.is_running():
        return {"status": "already_running"}

    if req.lead_ids:
        leads = [lead_repository.get(session, lid) for lid in req.lead_ids if lead_repository.get(session, lid) is not None]
    else:
        leads = lead_repository.get_pending(session, limit=req.daily_limit)

    if not leads:
        raise HTTPException(400, "No pending leads found.")

    accs = account_repository.get_active_accounts(session)
    if not accs:
        raise HTTPException(400, "No active email accounts configured.")

    if req.active_account_id:
        accs = [a for a in accs if a.id == req.active_account_id]
        if not accs:
            raise HTTPException(400, "Selected email account not found or inactive.")

    # Save preferences to settings model for persistence
    str_row = session.exec(select(Setting).where(Setting.key == "send_strategy")).first()
    if not str_row:
        session.add(Setting(key="send_strategy", value=req.strategy))
    else:
        str_row.value = req.strategy

    bs_row = session.exec(select(Setting).where(Setting.key == "batch_size")).first()
    if not bs_row:
        session.add(Setting(key="batch_size", value=str(req.batch_size)))
    else:
        bs_row.value = str(req.batch_size)
        
    session.commit()

    # Pass the current dictionary form of the settings so service doesn't query it inside thread
    runtime_cfg = {
        "send_strategy": req.strategy,
        "batch_size": str(req.batch_size),
        "groq_key": settings.groq_api_key,
        "openrouter_key": settings.openrouter_api_key,
        "apollo_key": settings.apollo_api_key,
        "calendar_url": settings.calendly_url,
        "sender_name": settings.sender_name,
        "sender_title": settings.sender_title,
        "llm_provider": settings.llm_provider,
        "openrouter_model": settings.openrouter_model
    }

    campaign_state.set_running(True)
    campaign_state.task = asyncio.create_task(
        campaign_service.run_campaign_batch(
            [l.id for l in leads],
            req.delay_seconds,
            [a.id for a in accs],
            runtime_cfg,
            broadcast,
            campaign_state.is_running
        )
    )
    return {"status": "started", "lead_count": len(leads), "strategy": req.strategy}

@router.post("/stop")
async def stop_campaign():
    global campaign_state
    campaign_state.set_running(False)
    task = campaign_state.task
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    return {"status": "stopping"}

@router.post("/preview/draft")
async def save_to_draft(req: DraftRequest, session: Session = Depends(get_db_session)):
    return {"status": "coming_soon"} # Reimplemented later via DraftService
