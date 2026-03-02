import io
import os
import shutil
import csv
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse
from sqlmodel import Session, select
from app.api.dependencies import get_db_session
from app.models.lead import Lead
from app.models.campaign import Campaign
from app.models.reply import Reply
from app.core.db import _DB_PATH

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
    res.headers["Content-Disposition"] = f"attachment; filename=leads_{int(datetime.now(timezone.utc).timestamp())}.csv"
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
    res.headers["Content-Disposition"] = f"attachment; filename=campaigns_{int(datetime.now(timezone.utc).timestamp())}.csv"
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
    res.headers["Content-Disposition"] = f"attachment; filename=replies_{int(datetime.now(timezone.utc).timestamp())}.csv"
    return res


@router.get("/backup")
def download_db_backup():
    """Download a full copy of the SQLite database for safe-keeping."""
    if not os.path.exists(_DB_PATH):
        raise HTTPException(status_code=404, detail="Database file not found")
    ts = int(datetime.now(timezone.utc).timestamp())
    return FileResponse(
        path=_DB_PATH,
        filename=f"cyberarc_backup_{ts}.db",
        media_type="application/octet-stream",
    )


@router.post("/restore")
async def restore_db_backup(file: UploadFile = File(...)):
    """Replace the active database with an uploaded .db backup file."""
    content = await file.read()
    # Validate magic bytes (SQLite format 3)
    if not content.startswith(b"SQLite format 3"):
        raise HTTPException(status_code=400, detail="Not a valid SQLite file")

    tmp_path = _DB_PATH + ".restore_tmp"
    bak_path = _DB_PATH + ".bak"
    try:
        with open(tmp_path, "wb") as f:
            f.write(content)
        if os.path.exists(_DB_PATH):
            shutil.copy2(_DB_PATH, bak_path)
        shutil.move(tmp_path, _DB_PATH)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {e}")

    return {"status": "restored", "message": "Database restored successfully. Restart the app to apply changes."}


@router.get("/info")
def db_info():
    """Return the path and size of the active database."""
    exists = os.path.exists(_DB_PATH)
    size_bytes = os.path.getsize(_DB_PATH) if exists else 0
    return {
        "db_path": _DB_PATH,
        "size_mb": f"{size_bytes / 1024 / 1024:.2f}",
        "exists":  exists,
    }
