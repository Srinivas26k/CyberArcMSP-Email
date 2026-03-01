from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from app.api.dependencies import get_db_session
from app.models.email_account import EmailAccount
from app.models.lead import Lead
from app.models.reply import Reply
from app.core.config import Settings

router = APIRouter()
_settings = Settings()

# Both /api/health and /api/health/ resolve here
@router.get("")
@router.get("/")
def health(session: Session = Depends(get_db_session)):
    accounts = session.exec(select(EmailAccount).where(EmailAccount.is_active)).all()
    leads    = session.exec(select(Lead)).all()
    return {
        "status":          "ok",
        "active_accounts": len(accounts),
        "leads_in_db":     len(leads),
        "version":         "2.1.1",
        "model":           _settings.openrouter_model or _settings.llm_provider,
    }

@router.get("/stats")
def dashboard_stats(session: Session = Depends(get_db_session)):
    leads    = session.exec(select(Lead)).all()
    replies  = session.exec(select(Reply)).all()
    accounts = session.exec(select(EmailAccount).where(EmailAccount.is_active)).all()

    total    = len(leads)
    pending  = sum(1 for lead in leads if lead.status == "pending")
    sent     = sum(1 for lead in leads if lead.status == "sent")
    failed   = sum(1 for lead in leads if lead.status == "failed")
    replied  = len(replies)

    return {
        "total_leads":     total,
        "pending":         pending,
        "sent":            sent,
        "failed":          failed,
        "replied":         replied,
        "active_accounts": len(accounts),
    }
