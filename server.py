"""
SRV AI Email Outreach — FastAPI Backend v1.0
Stack: FastAPI + O365 SMTP/IMAP + Groq/OpenRouter + Apollo.io
Raspberry Pi 5 ready (also works on any VPS/cloud)
"""

import asyncio
import json
import os
import re
import time
import imaplib
import smtplib
import email as email_lib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import decode_header
from collections import deque
from datetime import datetime, timezone
from typing import Optional
import httpx

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# ─────────────────────────────────────────────
# CONFIG  (override via .env or environment)
# ─────────────────────────────────────────────

def env(key, default=""):
    return os.environ.get(key, default)

GROQ_KEY        = env("GROQ_API_KEY")
OPENROUTER_KEY  = env("OPENROUTER_API_KEY")
APOLLO_KEY      = env("APOLLO_API_KEY")
CALENDLY_URL    = env("CALENDLY_URL", "https://calendly.com/cyberarcmsp/30min")
SENDER_NAME     = env("SENDER_NAME", "CyberArc MSP")
SENDER_TITLE    = env("SENDER_TITLE", "Enterprise Solutions Architect")

# O365 Mailboxes — loaded from OUTLOOK_ACCOUNTS JSON or individual vars
def load_o365_accounts():
    raw = env("OUTLOOK_ACCOUNTS")
    if raw:
        try:
            return json.loads(raw)
        except:
            pass
    accounts = []
    for i in range(1, 6):
        em = env(f"OUTLOOK_EMAIL_{i}")
        pw = env(f"OUTLOOK_PASS_{i}")
        nm = env(f"OUTLOOK_NAME_{i}")
        if em and pw:
            accounts.append({"email": em, "password": pw, "name": nm or em.split("@")[0]})
    return accounts

O365_ACCOUNTS = load_o365_accounts()

# ─────────────────────────────────────────────
# FASTAPI APP
# ─────────────────────────────────────────────

app = FastAPI(title="SRV AI Outreach", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─────────────────────────────────────────────
# IN-MEMORY STATE  (replace with SQLite/Postgres for production)
# ─────────────────────────────────────────────

leads_db: list[dict] = []          # All leads
outbox_db: list[dict] = []         # Queued / sent
sent_log: list[dict] = []          # Sent audit log
reply_log: list[dict] = []         # Detected replies
campaign_stats = {
    "total_sent": 0,
    "total_replies": 0,
    "total_leads": 0,
    "last_run": None,
}
_inbox_cursor = 0  # round-robin index

# ─────────────────────────────────────────────
# RATE LIMITER (per provider)
# ─────────────────────────────────────────────

class RateLimiter:
    def __init__(self, rpm: int):
        self.rpm = rpm
        self.window: deque = deque()
        self.lock = asyncio.Lock()
        self.last_call = 0.0

    async def acquire(self):
        async with self.lock:
            now = time.monotonic()
            # Purge timestamps older than 60s
            while self.window and now - self.window[0] > 60:
                self.window.popleft()
            if len(self.window) >= self.rpm:
                wait = 61 - (now - self.window[0])
                await asyncio.sleep(wait)
            gap = now - self.last_call
            if gap < 2.0:
                await asyncio.sleep(2.0 - gap)
            self.window.append(time.monotonic())
            self.last_call = time.monotonic()

_groq_limiter = RateLimiter(rpm=28)
_openrouter_limiter = RateLimiter(rpm=18)
_groq_sem = asyncio.Semaphore(1)
_openrouter_sem = asyncio.Semaphore(1)

# ─────────────────────────────────────────────
# LLM CLIENT
# ─────────────────────────────────────────────

GROQ_MODELS = [
    "moonshotai/kimi-k2-instruct-0905",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
]

async def call_groq(prompt: str, system: str) -> str:
    for model in GROQ_MODELS:
        for attempt in range(3):
            async with _groq_sem:
                await _groq_limiter.acquire()
                try:
                    async with httpx.AsyncClient(timeout=45) as client:
                        r = await client.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                            json={
                                "model": model,
                                "messages": [
                                    {"role": "system", "content": system},
                                    {"role": "user", "content": prompt},
                                ],
                                "temperature": 0.7,
                                "max_tokens": 1500,
                            }
                        )
                        if r.status_code == 429:
                            body = r.json() if r.headers.get("content-type","").startswith("application/json") else {}
                            wait = float(r.headers.get("Retry-After", 0))
                            if not wait:
                                m = re.search(r"try again in (\d+(?:\.\d+)?)s", str(body))
                                wait = float(m.group(1)) if m else (2 ** attempt * 2)
                            await asyncio.sleep(min(wait + 1, 30))
                            continue
                        if r.status_code == 200:
                            return r.json()["choices"][0]["message"]["content"]
                except Exception:
                    await asyncio.sleep(2 ** attempt)
    # Fallback to OpenRouter
    if OPENROUTER_KEY:
        return await call_openrouter(prompt, system)
    raise RuntimeError("All LLM providers failed")

async def call_openrouter(prompt: str, system: str) -> str:
    async with _openrouter_sem:
        await _openrouter_limiter.acquire()
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "meta-llama/llama-3.3-70b-instruct:free",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 1500,
                }
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

# ─────────────────────────────────────────────
# PROMPT ENGINEERING (ported from prompt.gs)
# ─────────────────────────────────────────────

SERVICE_PORTFOLIO = {
    "cybersecurity": "SOC/NOC 24/7 AI monitoring, VAPT, Zero Trust architecture, Cloud Security hardening (AWS/Azure/GCP).",
    "ai_toolkit": "AI Automation reducing overhead 40%, GovOps policy enforcement, AIOps event correlation.",
    "saas_services": "Custom multi-tenant platforms, GDPR/CCPA embedded architecture, Legacy modernization.",
    "audit_compliance": "GRC advisory for SOC 2, PCI DSS, HIPAA, GDPR, ISO 27001. IAM & privileged access.",
    "aiml_services": "Custom enterprise LLMs with safety rails, Data strategy with governance, Predictive analytics.",
    "cloud_devsecops": "Multi-cloud governance, DevSecOps CI/CD security gates, Terraform/Ansible IaC.",
    "c_level_advisory": "vCISO/vCIO strategic leadership, Board-level reporting, FinOps for CFOs.",
    "strategic_staffing": "Top 1% technical talent in Cybersecurity, AI, Cloud. Background vetting.",
    "corporate_training": "Cybersecurity awareness, Phishing defence, Certification validation.",
}

def get_smart_context(lead: dict) -> dict:
    text = (lead.get("company","") + " " + lead.get("industry","")).lower()
    role = lead.get("role","").lower()

    ctx = {
        "key": "generic",
        "hook": "Global operational pressure and digital transformation risk",
        "risk": "General Compliance & Data Governance",
        "services": [SERVICE_PORTFOLIO["c_level_advisory"], SERVICE_PORTFOLIO["cybersecurity"]],
    }

    if re.search(r"oil|gas|petro|energy", text):
        ctx.update(key="energy", hook="Critical OT/IT infrastructure convergence", risk="NERC CIP & HSE compliance")
        ctx["services"] = [SERVICE_PORTFOLIO["c_level_advisory"], SERVICE_PORTFOLIO["ai_toolkit"]]
    elif re.search(r"bank|financ|invest|capital|bfsi", text):
        ctx.update(key="bfsi", hook="High-frequency trading resilience & cross-border data flows", risk="SEC/GLBA/PCI DSS & SWIFT security")
        ctx["services"] = [SERVICE_PORTFOLIO["cybersecurity"], SERVICE_PORTFOLIO["audit_compliance"]]
    elif re.search(r"health|medic|pharma", text):
        ctx.update(key="healthcare", hook="Patient data integrity & medical IoT vulnerabilities", risk="HIPAA & PHI data governance")
        ctx["services"] = [SERVICE_PORTFOLIO["cybersecurity"], SERVICE_PORTFOLIO["audit_compliance"]]
    elif re.search(r"manufact|factory|steel|industr", text):
        ctx.update(key="manufacturing", hook="Smart factory & SCADA security risks", risk="IEC 62443 & IP protection")
        ctx["services"] = [SERVICE_PORTFOLIO["ai_toolkit"], SERVICE_PORTFOLIO["cloud_devsecops"]]
    elif re.search(r"saas|software|tech", text):
        ctx.update(key="saas", hook="Rapid scaling vs security debt accumulation", risk="SOC 2 Type II & data sovereignty")
        ctx["services"] = [SERVICE_PORTFOLIO["saas_services"], SERVICE_PORTFOLIO["aiml_services"]]

    if re.search(r"cfo|ceo|md|president", role):
        ctx["services"] = [SERVICE_PORTFOLIO["c_level_advisory"], SERVICE_PORTFOLIO["audit_compliance"]]
    elif re.search(r"ciso|security|risk", role):
        ctx["services"] = [SERVICE_PORTFOLIO["cybersecurity"], SERVICE_PORTFOLIO["audit_compliance"], SERVICE_PORTFOLIO["ai_toolkit"]]
    elif re.search(r"cto|cio|tech|engineer|architect", role):
        ctx["services"] = [SERVICE_PORTFOLIO["cloud_devsecops"], SERVICE_PORTFOLIO["aiml_services"]]

    ctx["services_text"] = "\n".join(f"- {s}" for s in ctx["services"])
    return ctx

def build_prompt(lead: dict) -> str:
    ctx = get_smart_context(lead)
    today = datetime.now().strftime("%B %d, %Y")
    return f"""
You are a Senior Partner at CyberArc MSP writing to {lead.get('first','there')} ({lead.get('role','')}) at {lead.get('company','')}.

TODAY'S DATE: {today}
RECIPIENT: {lead.get('company','')} | {lead.get('role','')} | {lead.get('industry','Technology')} | {lead.get('location','')}
INDUSTRY FOCUS: {ctx['key']} — {ctx['hook']}
COMPLIANCE ANGLE: {ctx['risk']}

AVAILABLE SERVICES:
{ctx['services_text']}

MISSION: Write a consultative B2B cold email (150-200 words).
- 50% Advanced Technology, 50% Risk Governance/Compliance
- Explicitly map CyberArc capabilities to this company's likely challenges
- Structure: Subject → Hi {lead.get('first','')}, → Correlation observation → 3 bullet points (Tech + Compliance) → Proof → CTA
- Subject under 60 chars, professional, impactful
- CTA: "Open for 15 mins this week?"

OUTPUT: Return ONLY valid JSON:
{{"subject":"...","bodyHtml":"...(HTML with <p><ul><li><strong> tags only, NO signature)"}}
""".strip()

# ─────────────────────────────────────────────
# EMAIL TEMPLATE
# ─────────────────────────────────────────────

def wrap_template(inner_html: str, sender_email: str) -> str:
    from datetime import datetime
    now = datetime.now()
    cal = f"{CALENDLY_URL}?month={now.year}-{now.month:02d}"
    return f"""
<div style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;background:#f4f6f8;padding:40px 0;">
  <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,.05);border:1px solid #e1e4e8;">
    <div style="padding:25px 40px;border-bottom:2px solid #0056b3;background:#fff;">
      <table style="width:100%;border-collapse:collapse;"><tr>
        <td style="width:50px;vertical-align:middle;">
          <img src="https://cyberarcmsp.com/logo.png" alt="CyberArc MSP" style="width:48px;height:auto;">
        </td>
        <td style="vertical-align:middle;padding-left:15px;">
          <span style="font-size:20px;font-weight:700;color:#333;letter-spacing:-.5px;">CyberArc MSP</span>
        </td>
      </tr></table>
    </div>
    <div style="padding:40px 40px 20px;color:#333;font-size:16px;line-height:1.6;">{inner_html}</div>
    <div style="margin:0 40px 30px;text-align:center;">
      <a href="{cal}" style="display:inline-block;padding:12px 24px;background:#0056b3;color:#fff;text-decoration:none;font-weight:600;border-radius:4px;font-size:15px;">📅 Book a Strategy Call</a>
    </div>
    <div style="background:#f8f9fa;padding:30px 40px;border-top:1px solid #eee;font-size:14px;color:#666;">
      <p style="margin:0 0 5px;"><strong style="color:#0056b3;font-size:16px;">{SENDER_NAME}</strong></p>
      <p style="margin:0 0 15px;color:#555;">{SENDER_TITLE}</p>
      <p style="margin:0;"><a href="https://cyberarcmsp.com" style="color:#0056b3;">{sender_email}</a></p>
      <div style="margin-top:20px;font-size:11px;color:#aaa;text-align:center;">
        © {now.year} CyberArc MSP. All rights reserved.
        <br>To unsubscribe, reply "Unsubscribe".
      </div>
    </div>
  </div>
</div>
""".strip()

# ─────────────────────────────────────────────
# O365 EMAIL SERVICE
# ─────────────────────────────────────────────

class O365Inbox:
    def __init__(self, config: dict):
        self.email    = config["email"]
        self.password = config["password"]
        self.name     = config.get("name", SENDER_NAME)

    def send(self, to: str, subject: str, html: str, plain: str) -> bool:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{self.name} <{self.email}>"
        msg["To"]      = to
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP("smtp.office365.com", 587, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(self.email, self.password)
            smtp.sendmail(self.email, to, msg.as_string())
        return True

    def test_connection(self) -> dict:
        try:
            with smtplib.SMTP("smtp.office365.com", 587, timeout=10) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(self.email, self.password)
            return {"ok": True, "email": self.email, "message": "SMTP connection successful"}
        except Exception as e:
            return {"ok": False, "email": self.email, "message": str(e)}

    def check_replies(self, since_days: int = 7) -> list[dict]:
        replies = []
        try:
            with imaplib.IMAP4_SSL("outlook.office365.com", 993) as imap:
                imap.login(self.email, self.password)
                imap.select("INBOX")
                _, msg_ids = imap.search(None, "UNSEEN")
                for mid in (msg_ids[0].split() if msg_ids[0] else []):
                    _, data = imap.fetch(mid, "(RFC822)")
                    raw = data[0][1]
                    msg = email_lib.message_from_bytes(raw)
                    subject = decode_header(msg["subject"] or "")[0][0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(errors="replace")
                    sender = msg.get("from", "")
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode(errors="replace")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode(errors="replace")
                    replies.append({
                        "from": sender,
                        "subject": subject,
                        "body": body[:500],
                        "inbox": self.email,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
        except Exception as e:
            pass
        return replies


class O365MultiInbox:
    def __init__(self, accounts: list[dict]):
        self.inboxes = [O365Inbox(a) for a in accounts]
        self._idx = 0
        self._lock = asyncio.Lock()

    async def next_inbox(self) -> O365Inbox:
        async with self._lock:
            inbox = self.inboxes[self._idx % len(self.inboxes)]
            self._idx += 1
            return inbox

    @property
    def count(self):
        return len(self.inboxes)


multi_inbox = O365MultiInbox(O365_ACCOUNTS) if O365_ACCOUNTS else None

# ─────────────────────────────────────────────
# APOLLO SEARCH
# ─────────────────────────────────────────────

INDUSTRY_MAP = {
    "banking": "Financial Services",
    "bank": "Financial Services",
    "bfsi": "Financial Services",
    "finance": "Financial Services",
    "fintech": "Financial Services",
    "insurance": "Insurance",
    "healthcare": "Hospital & Health Care",
    "health": "Hospital & Health Care",
    "pharma": "Pharmaceuticals",
    "saas": "Computer Software",
    "software": "Computer Software",
    "tech": "Information Technology and Services",
    "technology": "Information Technology and Services",
    "it": "Information Technology and Services",
    "manufacturing": "Mechanical or Industrial Engineering",
    "energy": "Oil & Energy",
    "oil": "Oil & Energy",
    "gas": "Oil & Energy",
    "telecom": "Telecommunications",
    "retail": "Retail",
    "education": "Education Management",
    "logistics": "Logistics and Supply Chain",
    "construction": "Construction",
    "real estate": "Real Estate",
    "media": "Media Production",
    "government": "Government Administration",
}

def normalise_locations(locs: list[str]) -> list[str]:
    result = []
    country_hints = {"mumbai": "India", "delhi": "India", "bangalore": "India",
                     "hyderabad": "India", "london": "United Kingdom", "dubai": "UAE"}
    for l in locs:
        l = l.strip().title()
        result.append(l)
        extra = country_hints.get(l.lower())
        if extra and extra not in result:
            result.append(extra)
    return list(dict.fromkeys(result))

async def apollo_search(titles: list[str], industry: str, locations: list[str],
                        seniority: list[str], per_page: int = 25) -> list[dict]:
    mapped_industry = INDUSTRY_MAP.get(industry.lower().strip(), industry)
    norm_locs = normalise_locations(locations)

    payload = {
        "api_key": APOLLO_KEY,
        "person_titles": titles,
        "person_seniority_tags": seniority or ["c_suite", "vp", "director"],
        "person_locations": norm_locs,
        "organization_locations": norm_locs,
        "q_organization_industries": [mapped_industry],
        "q_keywords": industry if mapped_industry == industry else "",
        "contact_email_status": ["verified", "likely to engage"],
        "per_page": per_page + 10,
        "page": 1,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.apollo.io/v1/mixed_people/search",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        r.raise_for_status()
        data = r.json()

    people = data.get("people", [])
    rows = []
    seen = set()
    for p in people:
        em = None
        for e in (p.get("email_status") and [p] or p.get("emails", [])):
            candidate = e if isinstance(e, str) else e.get("email")
            if candidate and candidate not in seen:
                em = candidate
                break
        if not em:
            em = p.get("email")
        if not em or em in seen:
            continue
        seen.add(em)
        org = p.get("organization", {}) or {}
        loc = ", ".join(filter(None, [p.get("city"), p.get("state"), p.get("country")]))
        ind = industry
        rows.append({
            "email": em,
            "first": p.get("first_name", ""),
            "last": p.get("last_name", ""),
            "company": org.get("name", ""),
            "role": p.get("title", ""),
            "website": org.get("website_url", ""),
            "linkedin": p.get("linkedin_url", ""),
            "location": loc,
            "seniority": p.get("seniority", ""),
            "employees": str(org.get("estimated_num_employees", "")),
            "industry": ind,
            "status": "pending",
        })
    return rows

# ─────────────────────────────────────────────
# PYDANTIC MODELS
# ─────────────────────────────────────────────

class ApolloQuery(BaseModel):
    titles: list[str]
    industry: str
    locations: list[str]
    seniority: list[str] = []
    per_page: int = 25

class SendRequest(BaseModel):
    lead_emails: list[str] = []
    daily_limit: int = 5
    delay_seconds: int = 65

class LeadImport(BaseModel):
    leads: list[dict]

class SettingsModel(BaseModel):
    groq_key: Optional[str] = None
    openrouter_key: Optional[str] = None
    apollo_key: Optional[str] = None
    calendly_url: Optional[str] = None
    sender_name: Optional[str] = None
    sender_title: Optional[str] = None
    accounts: Optional[list[dict]] = None

# ─────────────────────────────────────────────
# API ROUTES
# ─────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "inboxes": multi_inbox.count if multi_inbox else 0,
        "leads": len(leads_db),
        "outbox": len(outbox_db),
        "groq": bool(GROQ_KEY),
        "openrouter": bool(OPENROUTER_KEY),
        "apollo": bool(APOLLO_KEY),
    }

@app.get("/api/stats")
def stats():
    return {
        **campaign_stats,
        "leads": len(leads_db),
        "pending": sum(1 for l in outbox_db if l.get("status") == "pending"),
        "sent": sum(1 for l in outbox_db if l.get("status") == "sent"),
        "replied": len(reply_log),
        "inboxes": multi_inbox.count if multi_inbox else 0,
    }

@app.post("/api/apollo/search")
async def search_apollo(q: ApolloQuery):
    if not APOLLO_KEY:
        raise HTTPException(400, "Apollo API key not configured")
    results = await apollo_search(q.titles, q.industry, q.locations, q.seniority, q.per_page)
    # Add to leads_db (dedupe by email)
    existing = {l["email"] for l in leads_db}
    new_leads = [r for r in results if r["email"] not in existing]
    leads_db.extend(new_leads)
    campaign_stats["total_leads"] = len(leads_db)
    return {"found": len(results), "new": len(new_leads), "leads": results}

@app.get("/api/leads")
def get_leads():
    return {"leads": leads_db, "total": len(leads_db)}

@app.post("/api/leads/import")
def import_leads(body: LeadImport):
    existing = {l["email"] for l in leads_db}
    added = 0
    for lead in body.leads:
        if lead.get("email") and lead["email"] not in existing:
            lead["status"] = "pending"
            leads_db.append(lead)
            existing.add(lead["email"])
            added += 1
    campaign_stats["total_leads"] = len(leads_db)
    return {"added": added, "total": len(leads_db)}

@app.post("/api/leads/to-outbox")
def leads_to_outbox():
    pending = [l for l in leads_db if l.get("status") == "pending"]
    for l in pending:
        l["status"] = "queued"
        outbox_db.append({**l, "queued_at": datetime.now(timezone.utc).isoformat()})
    return {"queued": len(pending)}

@app.get("/api/outbox")
def get_outbox():
    return {"outbox": outbox_db, "total": len(outbox_db)}

@app.post("/api/send")
async def send_emails(req: SendRequest, background_tasks: BackgroundTasks):
    if not multi_inbox or multi_inbox.count == 0:
        raise HTTPException(400, "No O365 inboxes configured")
    background_tasks.add_task(_send_batch, req.daily_limit, req.delay_seconds)
    return {"status": "started", "limit": req.daily_limit}

async def _send_batch(limit: int, delay: int):
    global multi_inbox
    pending = [l for l in outbox_db if l.get("status") == "queued"][:limit]
    for i, lead in enumerate(pending):
        try:
            prompt = build_prompt(lead)
            system = "You are a B2B email expert. Output only valid JSON."
            raw = await call_groq(prompt, system)
            raw = re.sub(r"```json|```", "", raw).strip()
            start, end = raw.find("{"), raw.rfind("}")
            pkg = json.loads(raw[start:end+1])
            html_body = wrap_template(pkg["bodyHtml"], lead.get("email",""))
            plain = re.sub(r"<[^>]+>", "", pkg["bodyHtml"])

            inbox = await multi_inbox.next_inbox()
            inbox.send(lead["email"], pkg["subject"], html_body, plain)

            lead["status"] = "sent"
            lead["sent_at"] = datetime.now(timezone.utc).isoformat()
            lead["sent_from"] = inbox.email
            lead["subject"] = pkg["subject"]
            sent_log.append({**lead})
            campaign_stats["total_sent"] += 1
            campaign_stats["last_run"] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            lead["status"] = "error"
            lead["error"] = str(e)[:200]

        if i < len(pending) - 1:
            await asyncio.sleep(delay)

@app.post("/api/check-replies")
async def check_replies_endpoint():
    if not multi_inbox:
        raise HTTPException(400, "No inboxes configured")
    all_replies = []
    for inbox in multi_inbox.inboxes:
        replies = inbox.check_replies()
        all_replies.extend(replies)
    # Dedupe and store
    seen_ids = {r.get("from","") + r.get("subject","") for r in reply_log}
    new_replies = [r for r in all_replies if r.get("from","") + r.get("subject","") not in seen_ids]
    reply_log.extend(new_replies)
    campaign_stats["total_replies"] += len(new_replies)

    # Auto-reply
    auto_replied = 0
    for reply in new_replies:
        sender_email = re.findall(r"<([^>]+)>", reply.get("from",""))
        if sender_email:
            try:
                inbox = await multi_inbox.next_inbox()
                name_guess = reply["from"].split("<")[0].strip().split()[0] or "there"
                inbox.send(
                    sender_email[0],
                    f"Re: {reply['subject']}",
                    f"<p>Hi {name_guess},</p><p>Thank you for your response! I'd love to schedule a quick call. <a href='{CALENDLY_URL}'>Click here to book a time</a>.</p><p>Best,<br>{SENDER_NAME}</p>",
                    f"Hi {name_guess}, thanks for your response! Book a call: {CALENDLY_URL}"
                )
                auto_replied += 1
            except Exception:
                pass

    return {"new_replies": len(new_replies), "auto_replied": auto_replied, "total": len(reply_log)}

@app.get("/api/replies")
def get_replies():
    return {"replies": reply_log, "total": len(reply_log)}

@app.get("/api/sent")
def get_sent():
    return {"sent": sent_log, "total": len(sent_log)}

# O365 Management
@app.get("/api/o365/status")
def o365_status():
    if not multi_inbox:
        return {"configured": False, "count": 0, "accounts": []}
    return {
        "configured": True,
        "count": multi_inbox.count,
        "accounts": [{"email": i.email, "name": i.name, "index": idx}
                     for idx, i in enumerate(multi_inbox.inboxes)]
    }

@app.post("/api/o365/test/{index}")
def test_o365(index: int):
    if not multi_inbox or index >= multi_inbox.count:
        raise HTTPException(404, "Inbox not found")
    return multi_inbox.inboxes[index].test_connection()

@app.post("/api/o365/test-all")
def test_all_o365():
    if not multi_inbox:
        return {"results": []}
    return {"results": [i.test_connection() for i in multi_inbox.inboxes]}

@app.post("/api/generate-preview")
async def generate_preview(lead: dict):
    prompt = build_prompt(lead)
    raw = await call_groq(prompt, "You are a B2B email expert. Output only valid JSON.")
    raw = re.sub(r"```json|```", "", raw).strip()
    start, end = raw.find("{"), raw.rfind("}")
    pkg = json.loads(raw[start:end+1])
    return {
        "subject": pkg["subject"],
        "bodyHtml": wrap_template(pkg["bodyHtml"], lead.get("email", "contact@cyberarcmsp.com")),
    }

@app.post("/api/settings")
def save_settings(s: SettingsModel):
    global GROQ_KEY, OPENROUTER_KEY, APOLLO_KEY, CALENDLY_URL, SENDER_NAME, SENDER_TITLE
    global multi_inbox, O365_ACCOUNTS
    if s.groq_key:
        GROQ_KEY = s.groq_key
        os.environ["GROQ_API_KEY"] = s.groq_key
    if s.openrouter_key:
        OPENROUTER_KEY = s.openrouter_key
        os.environ["OPENROUTER_API_KEY"] = s.openrouter_key
    if s.apollo_key:
        APOLLO_KEY = s.apollo_key
        os.environ["APOLLO_API_KEY"] = s.apollo_key
    if s.calendly_url:
        CALENDLY_URL = s.calendly_url
    if s.sender_name:
        SENDER_NAME = s.sender_name
    if s.sender_title:
        SENDER_TITLE = s.sender_title
    if s.accounts:
        O365_ACCOUNTS = s.accounts
        multi_inbox = O365MultiInbox(O365_ACCOUNTS)
    return {"status": "saved", "inboxes": multi_inbox.count if multi_inbox else 0}

# Serve frontend
if os.path.exists("ui"):
    app.mount("/", StaticFiles(directory="ui", html=True), name="ui")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8002, reload=True)