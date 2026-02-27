"""
main.py — FastAPI application for SRV AI Email Outreach.
Entry point: uvicorn main:app --port 8002 --reload

All API routes + SSE stream + background campaign runner.
"""
import asyncio
import csv
import io
import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlmodel import Session, select

import database as db
import models as m
from apollo_search import apollo_search as _apollo_search
from company import COMPANY_PROFILE, SENDER_DEFAULTS, wrap_email_template
from email_engine import EmailEngine
from llm_client import generate_email
from prompt import build_email_prompt

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger("main")

# ─────────────────────────────────────────────────────────────────────────────
# ENV / RUNTIME CONFIG
# ─────────────────────────────────────────────────────────────────────────────

load_dotenv()

_cfg: dict = {}   # runtime mutable config, initialised on startup


def _load_env_cfg():
    """Load config from .env into _cfg. Called once at startup."""
    _cfg.update({
        "groq_key":         os.environ.get("GROQ_API_KEY", ""),
        "openrouter_key":   os.environ.get("OPENROUTER_API_KEY", ""),
        "apollo_key":       os.environ.get("APOLLO_API_KEY", ""),
        "calendar_url":     os.environ.get("CALENDLY_URL", COMPANY_PROFILE.get("calendly", "")),
        "sender_name":      os.environ.get("SENDER_NAME", SENDER_DEFAULTS["name"]),
        "sender_title":     os.environ.get("SENDER_TITLE", SENDER_DEFAULTS["title"]),
        "llm_provider":     os.environ.get("LLM_PROVIDER", "groq"),
        "openrouter_model": os.environ.get("OPENROUTER_MODEL", ""),
    })


def _load_settings_from_db(session: Session):
    """Override _cfg values from Settings table (user-saved via dashboard)."""
    # Key migration: old saves used Python attr names (underscores), new saves
    # use alias names (dashes). Remap old keys transparently.
    _old_to_new = {
        "s_company_name": "s-company-name",
        "s_tagline":      "s-tagline",
        "s_logo":         "s-logo",
        "s_website":      "s-website",
        "s_offices":      "s-offices",
        "calendly_url":   "calendar_url",
    }
    rows = session.exec(select(m.Setting)).all()
    for row in rows:
        key = _old_to_new.get(row.key, row.key)
        _cfg[key] = row.value


# ─────────────────────────────────────────────────────────────────────────────
# SSE EVENT BUS
# ─────────────────────────────────────────────────────────────────────────────

_sse_clients: list[asyncio.Queue] = []


async def _broadcast(event_type: str, data: dict):
    """Push an SSE event to all connected clients."""
    payload = json.dumps({"type": event_type, **data})
    dead = []
    for q in _sse_clients:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _sse_clients.remove(q)


# ─────────────────────────────────────────────────────────────────────────────
# CAMPAIGN STATE
# ─────────────────────────────────────────────────────────────────────────────

_campaign_running = False
_campaign_task: Optional[asyncio.Task] = None
_campaign_lock = asyncio.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# LIFESPAN (startup / shutdown)
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    _migrate_legacy_db_if_needed()
    db.init_db()
    _load_env_cfg()
    with Session(db.engine) as session:
        _load_settings_from_db(session)
    logger.info("✅ CA MSP AI Outreach started")
    yield
    logger.info("Shutting down…")


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI APP
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="CA MSP AI Outreach", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8002", "http://localhost:8002"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _html_to_plain(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html).replace("  ", " ").strip()


def _migrate_legacy_db_if_needed():
    """
    Preserve user data across upgrades by auto-migrating from known legacy DB
    locations when the current DB file does not yet exist.
    """
    target = db._DB_PATH
    if os.path.exists(target):
        return

    target_dir = os.path.dirname(target)
    os.makedirs(target_dir, exist_ok=True)

    here = os.path.dirname(os.path.abspath(__file__))
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(here, "database.db"),
        os.path.join(home, ".config", "CyberArc Outreach", "database.db"),
        os.path.join(home, ".local", "share", "CyberArc Outreach", "database.db"),
        os.path.join(home, ".config", "CA MSP AI Outreach", "database.db"),
        os.path.join(home, ".local", "share", "CA MSP AI Outreach", "database.db"),
    ]

    for source in candidates:
        if source == target:
            continue
        try:
            if os.path.exists(source) and os.path.getsize(source) > 0:
                shutil.copy2(source, target)
                logger.warning("Migrated legacy database from %s to %s", source, target)
                return
        except Exception as exc:
            logger.warning("Failed legacy DB migration from %s: %s", source, exc)


def _get_engine(session: Session) -> EmailEngine:
    """Build an EmailEngine from all active accounts in DB."""
    accs = session.exec(select(m.EmailAccount).where(m.EmailAccount.is_active == True)).all()
    strategy  = _cfg.get("send_strategy", "round_robin")
    batch_sz  = int(_cfg.get("batch_size", 5))
    return EmailEngine(
        [{"id": a.id, "email": a.email, "app_password": a.app_password,
          "provider": a.provider, "display_name": a.display_name} for a in accs],
        strategy=strategy,
        batch_size=batch_sz,
    )


def _lead_to_dict(lead: m.Lead) -> dict:
    return {
        "id":         lead.id,
        "email":      lead.email,
        "first_name": lead.first_name,
        "last_name":  lead.last_name,
        "company":    lead.company,
        "role":       lead.role,
        "industry":   lead.industry,
        "location":   lead.location,
        "seniority":  lead.seniority,
        "employees":  lead.employees,
        "website":    lead.website,
        "linkedin":   lead.linkedin,
        "status":     lead.status,
        "created_at": lead.created_at,
    }


def _account_to_dict(a: m.EmailAccount) -> dict:
    return {
        "id":           a.id,
        "email":        a.email,
        "provider":     a.provider,
        "display_name": a.display_name,
        "is_active":    a.is_active,
        "created_at":   a.created_at,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SSE STREAM
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/stream")
async def sse_stream():
    """
    Server-Sent Events endpoint. Connect once; receive all real-time events.
    Event format:  data: {"type": "lead_update"|"reply"|"stat"|"campaign_done", ...}\n\n
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    _sse_clients.append(queue)

    async def generator():
        # Send an immediate "connected" ping so the browser EventSource fires "open"
        yield "data: {\"type\": \"connected\"}\n\n"
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=25)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"   # SSE comment keeps connection alive
        except asyncio.CancelledError:
            pass
        finally:
            if queue in _sse_clients:
                _sse_clients.remove(queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH & STATS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health(session: Session = Depends(db.get_session)):
    accounts = session.exec(select(m.EmailAccount).where(m.EmailAccount.is_active == True)).all()
    leads    = session.exec(select(m.Lead)).all()
    return {
        "status":          "ok",
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "active_accounts": len(accounts),
        "total_leads":     len(leads),
        "groq_key":        bool(_cfg.get("groq_key")),
        "openrouter_key":  bool(_cfg.get("openrouter_key")),
        "apollo_key":      bool(_cfg.get("apollo_key")),
        "campaign_running": _campaign_running,
    }


@app.get("/api/stats")
def stats(session: Session = Depends(db.get_session)):
    leads   = session.exec(select(m.Lead)).all()
    replies = session.exec(select(m.Reply)).all()
    sent    = [l for l in leads if l.status == "sent"]
    pending = [l for l in leads if l.status == "pending"]
    failed  = [l for l in leads if l.status == "failed"]
    return {
        "total_leads":    len(leads),
        "pending":        len(pending),
        "sent":           len(sent),
        "replied":        len(replies),
        "failed":         len(failed),
        "active_accounts": len(session.exec(
            select(m.EmailAccount).where(m.EmailAccount.is_active == True)
        ).all()),
        "campaign_running": _campaign_running,
    }


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL ACCOUNTS
# ─────────────────────────────────────────────────────────────────────────────

class AccountIn(BaseModel):
    email:        str
    app_password: str
    provider:     str = "outlook"   # "gmail" | "outlook" | "m365" | "resend"
    display_name: str = ""


@app.get("/api/accounts")
def list_accounts(session: Session = Depends(db.get_session)):
    accs = session.exec(select(m.EmailAccount)).all()
    return {"accounts": [_account_to_dict(a) for a in accs]}


@app.post("/api/accounts", status_code=201)
def add_account(body: AccountIn, session: Session = Depends(db.get_session)):
    # Check for duplicate
    existing = session.exec(select(m.EmailAccount).where(m.EmailAccount.email == body.email)).first()
    if existing:
        raise HTTPException(400, f"Account {body.email} already exists")
    display = body.display_name or body.email.split("@")[0].title()
    acc = m.EmailAccount(
        email=body.email, app_password=body.app_password,
        provider=body.provider, display_name=display,
    )
    session.add(acc)
    session.commit()
    session.refresh(acc)
    return {"account": _account_to_dict(acc)}


@app.delete("/api/accounts/{account_id}")
def delete_account(account_id: int, session: Session = Depends(db.get_session)):
    acc = session.get(m.EmailAccount, account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    session.delete(acc)
    session.commit()
    return {"status": "deleted"}


@app.get("/api/accounts/detect-provider")
async def detect_provider(email: str):
    """
    Detect whether an email account is Gmail, M365 Business, or Outlook personal
    by probing SMTP connectivity (no credentials needed — just EHLO).

    Returns: { provider, label, description }
    """
    if not email or "@" not in email:
        raise HTTPException(400, "Invalid email address")

    domain = email.split("@")[1].lower()

    # Fast heuristics for known consumer domains
    GMAIL_DOMAINS = {"gmail.com", "googlemail.com"}
    OUTLOOK_CONSUMER = {"outlook.com", "hotmail.com", "live.com", "msn.com", "outlook.co.uk"}

    if domain in GMAIL_DOMAINS:
        return {"provider": "gmail", "label": "Gmail", "description": "Google Gmail SMTP (smtp.gmail.com)"}
    if domain in OUTLOOK_CONSUMER:
        return {"provider": "outlook", "label": "Outlook / O365 Personal", "description": "Microsoft consumer SMTP (smtp-mail.outlook.com)"}

    # For custom domains: probe smtp.office365.com first (M365 Business), then smtp-mail.outlook.com
    async def _probe(host: str, port: int = 587) -> bool:
        try:
            import asyncio
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=5
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    m365_ok = await _probe("smtp.office365.com", 587)
    if m365_ok:
        return {
            "provider": "m365",
            "label": "Microsoft 365 Business",
            "description": "M365 Business/Enterprise SMTP (smtp.office365.com). Tenant admin must enable SMTP AUTH.",
        }
    outlook_ok = await _probe("smtp-mail.outlook.com", 587)
    if outlook_ok:
        return {
            "provider": "outlook",
            "label": "Outlook / O365 Personal",
            "description": "Microsoft consumer/small-business SMTP (smtp-mail.outlook.com).",
        }

    # Final fallback — can't determine
    raise HTTPException(422, "Could not detect provider. Choose manually: try M365 Business for company emails.")


@app.post("/api/accounts/{account_id}/test")
def test_account(account_id: int, session: Session = Depends(db.get_session)):
    acc = session.get(m.EmailAccount, account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    from email_engine import SMTPAccount, ResendAccount
    AccountClass = ResendAccount if acc.provider == "resend" else SMTPAccount
    result = AccountClass({
        "email": acc.email, "app_password": acc.app_password,
        "provider": acc.provider, "display_name": acc.display_name,
    }).test_connection()
    return result


# ─────────────────────────────────────────────────────────────────────────────
# LEADS
# ─────────────────────────────────────────────────────────────────────────────

class LeadIn(BaseModel):
    email:      str
    first_name: str = ""
    last_name:  str = ""
    company:    str = ""
    role:       str = ""
    industry:   str = "Technology"
    location:   str = ""
    seniority:  str = ""
    employees:  str = ""
    website:    str = ""
    linkedin:   str = ""


@app.get("/api/leads")
def get_leads(session: Session = Depends(db.get_session)):
    leads = session.exec(select(m.Lead)).all()
    # Fetch campaigns and accounts to map sent_from
    campaigns = session.exec(select(m.Campaign)).all()
    accounts = {a.id: a.email for a in session.exec(select(m.EmailAccount)).all()}
    
    # map lead id to the latest campaign's account email
    sent_map = {}
    for c in campaigns:
        if c.account_id in accounts:
            sent_map[c.lead_id] = accounts[c.account_id]

    res = []
    for l in leads:
        d = _lead_to_dict(l)
        d["sent_from"] = sent_map.get(l.id, "—")
        res.append(d)

    return {"leads": res, "total": len(leads)}


@app.post("/api/leads", status_code=201)
def add_lead(body: LeadIn, session: Session = Depends(db.get_session)):
    existing = session.exec(select(m.Lead).where(m.Lead.email == body.email)).first()
    if existing:
        raise HTTPException(400, f"Lead {body.email} already exists")
    lead = m.Lead(**body.model_dump())
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return {"lead": _lead_to_dict(lead)}


@app.post("/api/leads/csv")
async def upload_csv(file: UploadFile = File(...), session: Session = Depends(db.get_session)):
    """
    Upload a CSV file to bulk-import leads.
    Required column: email
    Optional: first_name, last_name, company, role, industry, location,
              seniority, employees, website, linkedin
    CSV may also use legacy headers from Apps Script (First Name, Last Name, etc.)
    """
    content = await file.read()
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    ALIAS = {
        "first name": "first_name",  "firstname": "first_name",
        "last name":  "last_name",   "lastname":  "last_name",
        "job title":  "role",        "title":     "role",
        "num employees": "employees","# employees": "employees",
    }

    existing_emails = {l.email.lower() for l in session.exec(select(m.Lead)).all()}
    added = skipped = 0

    for row in reader:
        # Normalise header keys
        norm = {}
        for k, v in row.items():
            k_low = k.strip().lower()
            norm[ALIAS.get(k_low, k_low.replace(" ", "_"))] = (v or "").strip()

        email = norm.get("email", "").strip().lower()
        if not email or email in existing_emails:
            skipped += 1
            continue

        lead = m.Lead(
            email=email,
            first_name=norm.get("first_name", ""),
            last_name= norm.get("last_name", ""),
            company=   norm.get("company", ""),
            role=      norm.get("role", ""),
            industry=  norm.get("industry", "Technology"),
            location=  norm.get("location", ""),
            seniority= norm.get("seniority", ""),
            employees= norm.get("employees", ""),
            website=   norm.get("website", ""),
            linkedin=  norm.get("linkedin", ""),
        )
        session.add(lead)
        existing_emails.add(email)
        added += 1

    session.commit()
    total = session.exec(select(m.Lead)).all()
    return {"added": added, "skipped": skipped, "total": len(total)}


@app.delete("/api/leads/{lead_id}")
def delete_lead(lead_id: int, session: Session = Depends(db.get_session)):
    lead = session.get(m.Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    session.delete(lead)
    session.commit()
    return {"status": "deleted"}


@app.delete("/api/leads")
def delete_all_leads(session: Session = Depends(db.get_session)):
    leads = session.exec(select(m.Lead)).all()
    for l in leads:
        session.delete(l)
    session.commit()
    return {"deleted": len(leads)}


# ─────────────────────────────────────────────────────────────────────────────
# APOLLO SEARCH
# ─────────────────────────────────────────────────────────────────────────────

class ApolloQuery(BaseModel):
    titles:        list[str]
    industry:      str = ""
    locations:     list[str] = []
    company_sizes: list[str] = []
    target_count:  int = 10


@app.post("/api/apollo/search")
async def search_apollo(q: ApolloQuery, session: Session = Depends(db.get_session)):
    key = _cfg.get("apollo_key", "")
    if not key:
        raise HTTPException(400, "Apollo API key not configured. Set it in Settings.")

    try:
        results = await _apollo_search(
            api_key=key,
            titles=q.titles,
            industry=q.industry,
            locations=q.locations,
            company_sizes=q.company_sizes,
            target_count=q.target_count,
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))

    existing = {l.email.lower() for l in session.exec(select(m.Lead)).all()}
    added = 0
    newly_added_leads: list[dict] = []
    for r in results:
        email = r.get("email", "").lower()
        if not email or email in existing:
            continue
        lead = m.Lead(**{k: r.get(k, "") for k in [
            "email","first_name","last_name","company","role",
            "industry","location","seniority","employees","website","linkedin"
        ]})
        session.add(lead)
        existing.add(email)
        newly_added_leads.append(r)
        added += 1

    session.commit()
    # Always return ALL leads that Apollo found (new + already existing in DB)
    # so the Results panel always shows exactly what Apollo returned
    result_emails = {r.get("email", "").lower() for r in results}
    all_leads = session.exec(select(m.Lead)).all()
    display_leads = [_lead_to_dict(l) for l in all_leads
                     if l.email.lower() in result_emails]
    return {"found": len(results), "added": added, "leads": display_leads}


# ─────────────────────────────────────────────────────────────────────────────
# AI EMAIL PREVIEW
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/preview")
async def preview_email(lead: dict):
    sys_p, usr_p = build_email_prompt(lead)
    pkg = await generate_email(
        sys_p, usr_p,
        groq_key=_cfg.get("groq_key", ""),
        openrouter_key=_cfg.get("openrouter_key", ""),
        preferred_provider=_cfg.get("llm_provider", "groq"),
        openrouter_model=_cfg.get("openrouter_model") or None,
    )
    html = wrap_email_template(
        pkg["bodyHtml"],
        sender_email=_cfg.get("sender_email", SENDER_DEFAULTS["email"]),
        sender_name=_cfg.get("sender_name", SENDER_DEFAULTS["name"]),
        sender_title=_cfg.get("sender_title", SENDER_DEFAULTS["title"]),
        calendly_url=_cfg.get("calendar_url", COMPANY_PROFILE.get("calendly", "")),
    )
    return {"subject": pkg["subject"], "bodyHtml": html}


# ─────────────────────────────────────────────────────────────────────────────
# SAVE PREVIEW EMAIL TO DRAFT
# ─────────────────────────────────────────────────────────────────────────────

class DraftRequest(BaseModel):
    lead: dict
    account_id: Optional[int] = None   # None → pick first active account


@app.post("/api/preview/draft")
async def save_to_draft(req: DraftRequest, session: Session = Depends(db.get_session)):
    """
    Generate an email for the given lead data and save it to the sender
    account's Drafts folder via IMAP so the user can review/edit before sending.
    """
    # Pick account
    if req.account_id:
        acc = session.get(m.EmailAccount, req.account_id)
        if not acc:
            raise HTTPException(404, "Account not found")
    else:
        acc = session.exec(
            select(m.EmailAccount).where(m.EmailAccount.is_active == True)
        ).first()
        if not acc:
            raise HTTPException(400, "No active email accounts configured")

    if acc.provider == "resend":
        raise HTTPException(400, "Resend accounts are send-only and cannot save drafts. Use a Gmail or Outlook account.")

    # Generate the email content
    sys_p, usr_p = build_email_prompt(req.lead)
    pkg = await generate_email(
        sys_p, usr_p,
        groq_key=_cfg.get("groq_key", ""),
        openrouter_key=_cfg.get("openrouter_key", ""),
        preferred_provider=_cfg.get("llm_provider", "groq"),
        openrouter_model=_cfg.get("openrouter_model") or None,
    )
    html = wrap_email_template(
        pkg["bodyHtml"],
        sender_email=acc.email,
        sender_name=acc.display_name or _cfg.get("sender_name", SENDER_DEFAULTS["name"]),
        sender_title=_cfg.get("sender_title", SENDER_DEFAULTS["title"]),
        calendly_url=_cfg.get("calendar_url", COMPANY_PROFILE.get("calendly", "")),
        company_name=_cfg.get("s-company-name", COMPANY_PROFILE["name"]),
        company_tagline=_cfg.get("s-tagline", COMPANY_PROFILE["tagline"]),
        company_logo=_cfg.get("s-logo", COMPANY_PROFILE["logo_url"]),
        company_website=_cfg.get("s-website", COMPANY_PROFILE["website"]),
        offices=_cfg.get("s-offices", COMPANY_PROFILE["offices"]),
    )
    plain = _html_to_plain(pkg["bodyHtml"])

    # Determine the "To" address
    to_addr = req.lead.get("email", "")

    from email_engine import SMTPAccount
    smtp_acc = SMTPAccount({
        "email": acc.email, "app_password": acc.app_password,
        "provider": acc.provider, "display_name": acc.display_name,
    })

    try:
        await asyncio.to_thread(smtp_acc.save_draft, to_addr, pkg["subject"], html, plain)
    except Exception as exc:
        raise HTTPException(500, f"Failed to save draft: {exc}")

    return {
        "status": "saved",
        "subject": pkg["subject"],
        "saved_to": acc.email,
        "provider": acc.provider,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CAMPAIGN — START / STOP
# ─────────────────────────────────────────────────────────────────────────────

class CampaignRequest(BaseModel):
    strategy:          str = "round_robin"   # round_robin | parallel | batch_count
    batch_size:        int = 5               # for batch_count
    daily_limit:       int = 20
    delay_seconds:     int = 65
    lead_ids:          list[int] = []        # empty = all pending
    active_account_id: Optional[int] = None  # if set, use only this account


@app.post("/api/campaign/start")
async def start_campaign(req: CampaignRequest, session: Session = Depends(db.get_session)):
    global _campaign_running, _campaign_task

    async with _campaign_lock:
        if _campaign_running or (_campaign_task and not _campaign_task.done()):
            raise HTTPException(400, "A campaign is already running. Stop it first.")

        # Gather pending leads
        if req.lead_ids:
            leads = [session.get(m.Lead, lid) for lid in req.lead_ids]
            leads = [l for l in leads if l and l.status == "pending"]
        else:
            leads = session.exec(select(m.Lead).where(m.Lead.status == "pending")).all()

        leads = leads[:req.daily_limit]

        if not leads:
            raise HTTPException(400, "No pending leads found.")

        accs = session.exec(select(m.EmailAccount).where(m.EmailAccount.is_active == True)).all()
        if not accs:
            raise HTTPException(400, "No active email accounts configured.")

        # If a specific account is selected, restrict to that one
        if req.active_account_id:
            accs = [a for a in accs if a.id == req.active_account_id]
            if not accs:
                raise HTTPException(400, "Selected email account not found or inactive.")

        # Save strategy preferences to in-memory config
        _cfg["send_strategy"] = req.strategy
        _cfg["batch_size"] = req.batch_size

        _campaign_running = True
        _campaign_task = asyncio.create_task(
            _run_campaign(
                [l.id for l in leads],
                req.delay_seconds,
                [a.id for a in accs],
            )
        )
    return {"status": "started", "lead_count": len(leads), "strategy": req.strategy}


@app.post("/api/campaign/stop")
async def stop_campaign():
    global _campaign_running, _campaign_task

    _campaign_running = False
    task = _campaign_task
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    return {"status": "stopping"}


async def _run_campaign(lead_ids: list[int], delay: int, account_ids: list[int] | None = None):
    global _campaign_running, _campaign_task
    await _broadcast("stat", {"message": f"Campaign started for {len(lead_ids)} leads"})

    try:
        with Session(db.engine) as session:
            query = select(m.EmailAccount).where(m.EmailAccount.is_active == True)
            accs = session.exec(query).all()
            # Filter to selected account(s) if specified
            if account_ids:
                accs = [a for a in accs if a.id in account_ids]
            engine = EmailEngine(
                [{"id": a.id, "email": a.email, "app_password": a.app_password,
                  "provider": a.provider, "display_name": a.display_name} for a in accs],
                strategy=_cfg.get("send_strategy", "round_robin"),
                batch_size=int(_cfg.get("batch_size", 5)),
            )

        for lead_id in lead_ids:
            if not _campaign_running:
                break

            # Mark as drafting
            with Session(db.engine) as session:
                lead = session.get(m.Lead, lead_id)
                if not lead or lead.status != "pending":
                    continue
                lead.status = "drafting"
                session.add(lead)
                session.commit()
            await _broadcast("lead_update", {"lead_id": lead_id, "status": "drafting"})

            # Generate email
            try:
                with Session(db.engine) as session:
                    lead = session.get(m.Lead, lead_id)
                    lead_data = _lead_to_dict(lead)

                sys_p, usr_p = build_email_prompt(lead_data)
                pkg = await generate_email(
                    sys_p, usr_p,
                    groq_key=_cfg.get("groq_key", ""),
                    openrouter_key=_cfg.get("openrouter_key", ""),
                    preferred_provider=_cfg.get("llm_provider", "groq"),
                    openrouter_model=_cfg.get("openrouter_model") or None,
                )
                html_body = wrap_email_template(
                    pkg["bodyHtml"],
                    sender_email="{{SENDER_EMAIL}}",
                    sender_name="{{SENDER_NAME}}",
                    sender_title=_cfg.get("sender_title", SENDER_DEFAULTS["title"]),
                    calendly_url=_cfg.get("calendar_url", COMPANY_PROFILE.get("calendly", "")),
                    company_name=_cfg.get("s-company-name", COMPANY_PROFILE["name"]),
                    company_tagline=_cfg.get("s-tagline", COMPANY_PROFILE["tagline"]),
                    company_logo=_cfg.get("s-logo", COMPANY_PROFILE["logo_url"]),
                    company_website=_cfg.get("s-website", COMPANY_PROFILE["website"]),
                    offices=_cfg.get("s-offices", COMPANY_PROFILE["offices"]),
                )
                plain = _html_to_plain(pkg["bodyHtml"])

                # Send (engine picks the right account based on strategy)
                results = await engine.send_batch(
                    jobs=[{"to": lead_data["email"], "subject": pkg["subject"],
                           "html": html_body, "plain": plain, "lead_id": lead_id}],
                    delay_seconds=0,
                )
                result = results[0]

                # Persist result
                with Session(db.engine) as session:
                    lead = session.get(m.Lead, lead_id)
                    if result["success"]:
                        lead.status = "sent"
                        acc = session.exec(
                            select(m.EmailAccount).where(m.EmailAccount.email == result["sent_from"])
                        ).first()
                        campaign = m.Campaign(
                            lead_id=lead_id,
                            account_id=acc.id if acc else None,
                            subject=pkg["subject"],
                            sent_at=datetime.now(timezone.utc).isoformat(),
                        )
                        session.add(campaign)
                    else:
                        lead.status = "failed"
                        campaign = m.Campaign(
                            lead_id=lead_id,
                            error_message=result.get("error", "Unknown error"),
                            sent_at=datetime.now(timezone.utc).isoformat(),
                        )
                        session.add(campaign)
                    session.add(lead)
                    session.commit()

                status = "sent" if result["success"] else "failed"
                await _broadcast("lead_update", {"lead_id": lead_id, "status": status,
                                                  "sent_from": result.get("sent_from", ""),
                                                  "subject": pkg.get("subject", "")})

            except Exception as exc:
                logger.error(f"Campaign error on lead {lead_id}: {exc}")
                with Session(db.engine) as session:
                    lead = session.get(m.Lead, lead_id)
                    if lead:
                        lead.status = "failed"
                        session.add(lead)
                        session.commit()
                await _broadcast("lead_update", {"lead_id": lead_id, "status": "failed",
                                                  "error": str(exc)[:200]})

            await asyncio.sleep(delay)

    finally:
        _campaign_running = False
        _campaign_task = None
        await _broadcast("campaign_done", {"message": "Campaign finished"})
        await _broadcast("stat", {"refresh": True})
        logger.info("Campaign complete")


# ─────────────────────────────────────────────────────────────────────────────
# REPLIES
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/replies/check")
async def check_replies(session: Session = Depends(db.get_session)):
    engine = _get_engine(session)
    if not engine.accounts:
        raise HTTPException(400, "No active email accounts to check.")

    new_replies = await engine.check_all_replies()

    # Dedupe against existing
    existing_keys = {
        f"{r.from_email}|{r.subject}"
        for r in session.exec(select(m.Reply)).all()
    }

    added = 0
    for rep in new_replies:
        key = f"{rep['from_email']}|{rep['subject']}"
        if key in existing_keys:
            continue

        # Try to match to a known lead
        lead = session.exec(
            select(m.Lead).where(m.Lead.email == rep["from_email"].lower())
        ).first()
        if lead:
            lead.status = "replied"
            session.add(lead)

        reply_row = m.Reply(
            lead_id=     lead.id if lead else None,
            from_email=  rep["from_email"],
            from_name=   rep["from_name"],
            subject=     rep["subject"],
            snippet=     rep["snippet"],
            inbox_account=rep["inbox_account"],
        )
        session.add(reply_row)
        existing_keys.add(key)
        added += 1

        await _broadcast("reply", {
            "from_email": rep["from_email"],
            "from_name":  rep["from_name"],
            "subject":    rep["subject"],
            "snippet":    rep["snippet"][:200],
        })
        if lead:
            await _broadcast("lead_update", {"lead_id": lead.id, "status": "replied"})

    session.commit()
    await _broadcast("stat", {"refresh": True})
    return {"new_replies": added, "total": session.exec(select(m.Reply)).all().__len__()}


@app.get("/api/replies")
def get_replies(session: Session = Depends(db.get_session)):
    replies = session.exec(select(m.Reply)).all()
    return {"replies": [
        {
            "id":           r.id,
            "lead_id":      r.lead_id,
            "from_email":   r.from_email,
            "from_name":    r.from_name,
            "subject":      r.subject,
            "snippet":      r.snippet,
            "inbox_account":r.inbox_account,
            "received_at":  r.received_at,
        } for r in replies
    ], "total": len(replies)}


# ─────────────────────────────────────────────────────────────────────────────
# SETTINGS
# ─────────────────────────────────────────────────────────────────────────────

class SettingsIn(BaseModel):
    groq_key:         Optional[str] = None
    openrouter_key:   Optional[str] = None
    apollo_key:       Optional[str] = None
    calendar_url:     Optional[str] = None   # provider-neutral booking link
    sender_name:      Optional[str] = None
    sender_title:     Optional[str] = None
    sender_email:     Optional[str] = None
    llm_provider:     Optional[str] = None   # "groq" | "openrouter"
    openrouter_model: Optional[str] = None
    send_strategy:    Optional[str] = None
    batch_size:       Optional[int] = None
    delay_seconds:    Optional[int] = None
    # Brand Customization
    s_company_name: Optional[str] = Field(default=None, alias="s-company-name")
    s_tagline: Optional[str] = Field(default=None, alias="s-tagline")
    s_logo: Optional[str] = Field(default=None, alias="s-logo")
    s_website: Optional[str] = Field(default=None, alias="s-website")
    s_offices: Optional[str] = Field(default=None, alias="s-offices")


@app.get("/api/settings")
def get_settings():
    # Return non-secret config (mask keys)
    def mask(v: str) -> str:
        return v[:4] + "…" + v[-4:] if v and len(v) > 10 else ("✓ set" if v else "")
    return {
        "groq_key":         mask(_cfg.get("groq_key", "")),
        "openrouter_key":   mask(_cfg.get("openrouter_key", "")),
        "apollo_key":       mask(_cfg.get("apollo_key", "")),
        "calendar_url":     _cfg.get("calendar_url", ""),
        "sender_name":      _cfg.get("sender_name", ""),
        "sender_title":     _cfg.get("sender_title", ""),
        "sender_email":     _cfg.get("sender_email", ""),
        "llm_provider":     _cfg.get("llm_provider", "groq"),
        "openrouter_model": _cfg.get("openrouter_model", ""),
        "send_strategy":    _cfg.get("send_strategy", "round_robin"),
        "batch_size":       _cfg.get("batch_size", 5),
        "s-company-name":   _cfg.get("s-company-name", ""),
        "s-tagline":        _cfg.get("s-tagline", ""),
        "s-logo":           _cfg.get("s-logo", ""),
        "s-website":        _cfg.get("s-website", ""),
        "s-offices":        _cfg.get("s-offices", ""),
    }


@app.post("/api/settings")
def save_settings(body: SettingsIn, session: Session = Depends(db.get_session)):
    # IMPORTANT: must use by_alias=True so keys like 's-company-name' (alias)
    # are stored instead of 's_company_name' (Python attr name), matching _cfg.get() reads.
    updates = body.model_dump(by_alias=True, exclude_none=True)
    for key, value in updates.items():
        _cfg[key] = value
        # Persist to DB
        row = session.exec(select(m.Setting).where(m.Setting.key == key)).first()
        if row:
            row.value = str(value)
        else:
            session.add(m.Setting(key=key, value=str(value)))
    session.commit()
    return {"status": "saved", "updated_keys": list(updates.keys())}


# ─────────────────────────────────────────────────────────────────────────────
# DATA EXPORT & BACKUP
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/leads/export")
def export_leads_csv(session: Session = Depends(db.get_session)):
    """Download all leads as a CSV file for record-keeping."""
    leads = session.exec(select(m.Lead)).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "email", "first_name", "last_name", "company", "role",
                     "industry", "location", "seniority", "employees", "website",
                     "linkedin", "status", "created_at"])
    for l in leads:
        writer.writerow([
            l.id, l.email, l.first_name, l.last_name, l.company, l.role,
            l.industry, l.location, l.seniority, l.employees, l.website,
            l.linkedin, l.status, l.created_at,
        ])
    output.seek(0)
    filename = f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/campaigns/export")
def export_campaigns_csv(session: Session = Depends(db.get_session)):
    """Download all sent campaign records as CSV."""
    campaigns = session.exec(select(m.Campaign)).all()
    leads_map = {l.id: l for l in session.exec(select(m.Lead)).all()}
    accs_map  = {a.id: a for a in session.exec(select(m.EmailAccount)).all()}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["campaign_id", "lead_email", "lead_name", "company", "role",
                     "subject", "sent_from_account", "sent_at", "error"])
    for c in campaigns:
        lead = leads_map.get(c.lead_id)
        acc  = accs_map.get(c.account_id)
        writer.writerow([
            c.id,
            lead.email      if lead else "",
            f"{lead.first_name} {lead.last_name}".strip() if lead else "",
            lead.company    if lead else "",
            lead.role       if lead else "",
            c.subject       or "",
            acc.email       if acc else "",
            c.sent_at       or "",
            c.error_message or "",
        ])
    output.seek(0)
    filename = f"campaigns_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/replies/export")
def export_replies_csv(session: Session = Depends(db.get_session)):
    """Download all replies as CSV."""
    replies = session.exec(select(m.Reply)).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "from_email", "from_name", "subject", "snippet",
                     "inbox_account", "received_at"])
    for r in replies:
        writer.writerow([r.id, r.from_email, r.from_name, r.subject,
                         r.snippet, r.inbox_account, r.received_at])
    output.seek(0)
    filename = f"replies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/db/info")
def db_info():
    """Return the database file path and size — useful for support and troubleshooting."""
    db_path = db._DB_PATH
    exists  = os.path.exists(db_path)
    size_mb = round(os.path.getsize(db_path) / 1024 / 1024, 3) if exists else 0
    return {
        "db_path":  db_path,
        "exists":   exists,
        "size_mb":  size_mb,
        "data_dir": os.path.dirname(db_path),
    }


@app.get("/api/db/backup")
def download_database_backup():
    """
    Download the raw SQLite database file.
    This is the complete backup of all leads, campaigns, replies, accounts and settings.
    Useful for migrating to a new machine or restoring data after a reinstall.
    """
    db_path = db._DB_PATH
    if not os.path.exists(db_path):
        raise HTTPException(404, "Database file not found")
    filename = f"cyberarc_outreach_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    return FileResponse(
        db_path,
        media_type="application/octet-stream",
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/api/db/restore")
async def restore_database_backup(file: UploadFile = File(...)):
    """
    Upload a previously downloaded .db backup file to restore all data.
    The server is restarted automatically after restore via process replacement.
    """
    if _campaign_running:
        raise HTTPException(409, "Stop the running campaign before restoring a backup.")

    if not file.filename.endswith('.db'):
        raise HTTPException(400, "File must be a .db SQLite backup")
    max_size_bytes = 512 * 1024 * 1024
    total_bytes = 0
    db_path = db._DB_PATH
    db_dir = os.path.dirname(db_path)
    os.makedirs(db_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".restore.db", dir=db_dir) as tmp:
        tmp_path = tmp.name
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > max_size_bytes:
                os.unlink(tmp_path)
                raise HTTPException(400, "Backup file is too large.")
            tmp.write(chunk)

    if total_bytes < 100:
        os.unlink(tmp_path)
        raise HTTPException(400, "File is too small to be a valid database")

    with open(tmp_path, "rb") as f:
        header = f.read(16)
    if header != b"SQLite format 3\x00":
        os.unlink(tmp_path)
        raise HTTPException(400, "File does not appear to be a valid SQLite database")

    try:
        conn = sqlite3.connect(f"file:{tmp_path}?mode=ro", uri=True)
        try:
            check = conn.execute("PRAGMA integrity_check;").fetchone()
        finally:
            conn.close()
        if not check or check[0] != "ok":
            os.unlink(tmp_path)
            raise HTTPException(400, "Backup integrity check failed.")
    except HTTPException:
        raise
    except Exception as exc:
        os.unlink(tmp_path)
        raise HTTPException(400, f"Could not validate backup: {exc}")

    backup_path = f"{db_path}.pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    try:
        db.engine.dispose()
        if os.path.exists(db_path):
            shutil.copy2(db_path, backup_path)
        os.replace(tmp_path, db_path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return {
        "status": "restored",
        "message": "Database restored successfully. Please restart the application to reload all data.",
        "db_path": db_path,
        "previous_backup_path": backup_path if os.path.exists(backup_path) else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SERVE FRONTEND
# ─────────────────────────────────────────────────────────────────────────────

_here = os.path.dirname(os.path.abspath(__file__))
_UI_DIR = os.path.join(_here, "ui")

# In some packaged layouts the ui folder may be placed differently
if not os.path.isdir(_UI_DIR):
    _alt1 = os.path.join(_here, "..", "ui")        # one level up
    _alt2 = os.path.join(_here, "..", "app", "ui")  # resources/app/ui
    if os.path.isdir(_alt1):
        _UI_DIR = os.path.abspath(_alt1)
    elif os.path.isdir(_alt2):
        _UI_DIR = os.path.abspath(_alt2)

logger.info(f"UI directory: {_UI_DIR} (exists={os.path.isdir(_UI_DIR)})")
if os.path.isdir(_UI_DIR):
    app.mount("/", StaticFiles(directory=_UI_DIR, html=True), name="ui")
else:
    logger.warning("UI directory not found — frontend will not be served. Check packaging.")


# ─────────────────────────────────────────────────────────────────────────────
# DEV ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
