from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from app.api.dependencies import get_db_session
from app.models.email_account import EmailAccount
from app.models.lead import Lead

router = APIRouter()

@router.get("/health")
def health(session: Session = Depends(get_db_session)):
    accounts = session.exec(select(EmailAccount).where(EmailAccount.is_active)).all()
    leads = session.exec(select(Lead)).all()
    return {
        "status": "ok",
        "accounts_connected": len(accounts),
        "leads_in_db": len(leads),
        "version": "2.1.1" # Standardized version tag
    }

@router.get("/stats")
def dashboard_stats(session: Session = Depends(get_db_session)):
    leads = session.exec(select(Lead)).all()
    total = len(leads)
    pending = sum(1 for lead in leads if lead.status == "pending")
    drafting = sum(1 for lead in leads if lead.status == "drafting")
    sent = sum(1 for lead in leads if lead.status == "sent")
    failed = sum(1 for lead in leads if lead.status == "failed")
    
    accounts = session.exec(select(EmailAccount).where(EmailAccount.is_active)).all()
    
    return {
        "total": total,
        "pending": pending,
        "drafting": drafting,
        "sent": sent,
        "failed": failed,
        "active_accounts": len(accounts),
        "campaign_running": False # TODO: Wire to CampaignService state
    }
