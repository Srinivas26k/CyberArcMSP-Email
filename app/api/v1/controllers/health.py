from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from app.api.dependencies import get_db_session
from app.models.email_account import EmailAccount
from app.models.lead import Lead
from app.models.reply import Reply
from app.models.campaign import Campaign
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
        "version":         "2.2.0",
        "model":           _settings.openrouter_model or _settings.llm_provider,
    }

@router.get("/stats")
def dashboard_stats(session: Session = Depends(get_db_session)):
    leads     = session.exec(select(Lead)).all()
    replies   = session.exec(select(Reply)).all()
    accounts  = session.exec(select(EmailAccount).where(EmailAccount.is_active)).all()
    campaigns = session.exec(select(Campaign)).all()

    total          = len(leads)
    pending        = sum(1 for ld in leads if ld.status == "pending")
    sent           = sum(1 for ld in leads if ld.status == "sent")
    opened         = sum(1 for ld in leads if ld.status == "opened")
    failed         = sum(1 for ld in leads if ld.status == "failed")
    unsubscribed   = sum(1 for ld in leads if ld.status == "unsubscribed")
    replied        = len(replies)
    total_opens    = sum((c.open_count or 0) for c in campaigns)
    sent_campaigns = sum(1 for c in campaigns if c.sent_at)
    open_rate      = round((sum(1 for c in campaigns if c.opened_at) / sent_campaigns * 100), 1) if sent_campaigns else 0

    # Sequence stats
    try:
        from app.models.sequence import SequenceEnrollment
        enrollments = session.exec(select(SequenceEnrollment)).all()
        seq_active  = sum(1 for e in enrollments if e.status == "active")
    except Exception:
        seq_active  = 0

    return {
        "total_leads":     total,
        "pending":         pending,
        "sent":            sent,
        "opened":          opened,
        "failed":          failed,
        "unsubscribed":    unsubscribed,
        "replied":         replied,
        "total_opens":     total_opens,
        "open_rate":       open_rate,
        "active_accounts": len(accounts),
        "seq_active":      seq_active,
    }
