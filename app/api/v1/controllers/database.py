import os
import io
import csv
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from app.api.dependencies import get_db_session
from app.models.lead import Lead
from app.models.campaign import Campaign
from app.models.reply import Reply

router = APIRouter()

@router.get("/leads/export")
def export_leads_csv(session: Session = Depends(get_db_session)):
    leads = session.exec(select(Lead)).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "email", "first_name", "last_name", "company", "role", 
                     "industry", "location", "seniority", "employees", "website", 
                     "linkedin", "status", "created_at"])
    for lead in leads:
        writer.writerow([
            lead.id, lead.email, lead.first_name, lead.last_name, lead.company, lead.role,
            lead.industry, lead.location, lead.seniority, lead.employees, lead.website,
            lead.linkedin, lead.status, lead.created_at
        ])
    res = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    res.headers["Content-Disposition"] = f"attachment; filename=leads_export_{int(datetime.now(timezone.utc).timestamp())}.csv"
    return res

@router.get("/campaigns/export")
def export_campaigns_csv(session: Session = Depends(get_db_session)):
    campaigns = session.exec(select(Campaign)).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "lead_id", "account_id", "subject", "sent_at", "error_message"])
    for cmp in campaigns:
        writer.writerow([
            cmp.id, cmp.lead_id, cmp.account_id, cmp.subject, cmp.sent_at, cmp.error_message
        ])
    res = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    res.headers["Content-Disposition"] = f"attachment; filename=campaigns_export_{int(datetime.now(timezone.utc).timestamp())}.csv"
    return res

@router.get("/replies/export")
def export_replies_csv(session: Session = Depends(get_db_session)):
    replies = session.exec(select(Reply)).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "lead_id", "from_email", "from_name", "subject", "snippet", "inbox_account", "received_at"])
    for rep in replies:
        writer.writerow([
            rep.id, rep.lead_id, rep.from_email, rep.from_name, rep.subject, rep.snippet, rep.inbox_account, rep.received_at
        ])
    res = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    res.headers["Content-Disposition"] = f"attachment; filename=replies_export_{int(datetime.now(timezone.utc).timestamp())}.csv"
    return res
