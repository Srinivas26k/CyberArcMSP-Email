from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlmodel import Session, select
from app.api.dependencies import get_db_session
from app.models.lead import Lead
from app.models.campaign import Campaign
from app.schemas.lead import LeadIn, ApolloQuery
from app.services.lead_service import lead_service
from app.utils.apollo_search import apollo_search as _apollo_search
from app.utils.scoring import score_lead
from app.repositories.lead_repository import lead_repository
import re

router = APIRouter()


def _lead_to_dict(lead: Lead) -> dict:
    """Full lead dict — all fields, used for API responses and LLM context."""
    return {
        "id":              lead.id,
        "email":           lead.email,
        "first_name":      lead.first_name,
        "last_name":       lead.last_name,
        "company":         lead.company,
        "role":            lead.role,
        "industry":        lead.industry,
        "location":        lead.location,
        "seniority":       lead.seniority,
        "employees":       lead.employees,
        "website":         lead.website,
        "linkedin":        lead.linkedin,
        "headline":        lead.headline,
        "phone":           lead.phone,
        "departments":     lead.departments,
        "org_industry":    lead.org_industry,
        "org_founded":     lead.org_founded,
        "org_description": lead.org_description,
        "org_funding":     lead.org_funding,
        "org_tech_stack":  lead.org_tech_stack,
        "status":          lead.status,
        "draft_subject":   lead.draft_subject,
        "draft_body":      lead.draft_body,
        "created_at":      lead.created_at,
        "lead_score":      getattr(lead, "lead_score", 0) or 0,
        "is_unsubscribed": getattr(lead, "is_unsubscribed", False) or False,
    }


def _load_cfg(session: Session) -> dict:
    """Load LLM + campaign config from the settings table."""
    import json
    from app.models.setting import Setting
    SENSITIVE = {"groq_key", "openrouter_key", "apollo_key", "llm_providers"}
    rows = session.exec(select(Setting)).all()
    cfg: dict = {}
    for row in rows:
        cfg[row.key] = row.get_decrypted_value() if row.key in SENSITIVE else row.value

    # Parse llm_providers JSON → list of {provider, api_key, model} dicts
    raw = cfg.pop("llm_providers", "") or ""
    if raw:
        try:
            cfg["providers"] = json.loads(raw)
        except Exception:
            cfg["providers"] = []
    else:
        # Backward compat: build providers list from legacy individual keys.
        # Flag this so callers can give a better error message.
        cfg["_legacy_keys"] = True
        legacy: list[dict] = []
        groq_k = cfg.get("groq_key", "").strip()
        or_k   = cfg.get("openrouter_key", "").strip()
        if groq_k:
            legacy.append({"provider": "groq", "api_key": groq_k, "model": ""})
        # Only add openrouter slot if the key is different from the groq key
        # (a common mis-save where the same key ends up in both fields).
        if or_k and or_k != groq_k:
            legacy.append({"provider": "openrouter", "api_key": or_k,
                           "model": cfg.get("openrouter_model", "")})
        cfg["providers"] = legacy
    return cfg


def _get_identity_and_services(session: Session):
    """Return (identity, services) from DB.
    Falls back to empty placeholder values if onboarding hasn't been completed.
    """
    from app.models.identity import IdentityProfile, KnowledgeBase
    identity = session.exec(select(IdentityProfile)).first()
    if not identity:
        # Onboarding not yet completed — use empty identity so LLM uses generic language
        identity = IdentityProfile(name="", tagline="", website="",
                                   logo_url="", calendly_url="",
                                   sender_name="", sender_title="")
        services = []
    else:
        services = session.exec(
            select(KnowledgeBase).where(KnowledgeBase.identity_id == identity.id).limit(10)
        ).all()
    return identity, services

def _offices_to_str(offices) -> str:
    """Convert IdentityProfile.offices (List[dict] | List[str] | str) to a plain bullet string."""
    if isinstance(offices, list):
        return " • ".join(
            (o.get("city") or o.get("name") or str(o)) if isinstance(o, dict) else str(o)
            for o in offices if o
        ) or ""
    return str(offices) if offices else ""


@router.get("/")
def list_leads(session: Session = Depends(get_db_session)):
    from sqlmodel import desc
    from app.models.email_account import EmailAccount
    leads = lead_repository.get_all(session)
    # Fetch latest error + sent_at + sent_from per lead from campaigns table
    all_campaigns = session.exec(select(Campaign).order_by(desc(Campaign.id))).all()
    error_map: dict = {}  # lead_id -> last error_message
    sent_map:  dict = {}  # lead_id -> last sent_at
    sent_from_map: dict = {}  # lead_id -> sender email
    account_ids_needed: set = set()
    for c in all_campaigns:
        if c.lead_id not in error_map:
            error_map[c.lead_id] = c.error_message or ""
        if c.lead_id not in sent_map:
            sent_map[c.lead_id] = c.sent_at or ""
        if c.lead_id not in sent_from_map and c.account_id:
            sent_from_map[c.lead_id] = c.account_id
            account_ids_needed.add(c.account_id)
    # Resolve account_id -> email in bulk
    account_email_map: dict = {}
    if account_ids_needed:
        accs = session.exec(select(EmailAccount).where(EmailAccount.id.in_(account_ids_needed))).all()  # type: ignore[attr-defined]
        account_email_map = {a.id: a.email for a in accs}
    res = []
    for lead in leads:
        d = _lead_to_dict(lead)
        d["last_error"] = error_map.get(lead.id, "")
        d["last_sent_at"] = sent_map.get(lead.id, "")
        aid = sent_from_map.get(lead.id)
        d["sent_from"] = account_email_map.get(aid, "") if aid else ""
        res.append(d)
    return {"leads": res, "total": len(res)}

@router.post("/", status_code=201)
def add_lead(body: LeadIn, session: Session = Depends(get_db_session)):
    existing = lead_repository.get_by_email(session, body.email)
    if existing:
        raise HTTPException(400, f"Lead {body.email} already exists")

    lead = Lead(**body.model_dump())
    lead.lead_score = score_lead(body.model_dump())
    lead = lead_repository.create(session, lead)
    return {"lead": _lead_to_dict(lead)}

@router.post("/csv")
async def upload_csv(file: UploadFile = File(...), session: Session = Depends(get_db_session)):
    content = await file.read()
    return lead_service.process_csv_upload(session, content)

@router.delete("/{lead_id}")
def delete_lead(lead_id: int, session: Session = Depends(get_db_session)):
    lead = lead_repository.get(session, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    lead_repository.remove(session, lead_id)
    return {"status": "deleted"}

@router.delete("/")
def delete_all_leads(session: Session = Depends(get_db_session)):
    leads = lead_repository.get_all(session)
    for lead in leads:
        lead_repository.remove(session, lead.id)
    return {"deleted": len(leads)}

@router.post("/apollo/search")
async def search_apollo(q: ApolloQuery, session: Session = Depends(get_db_session)):
    cfg = _load_cfg(session)
    key = cfg.get("apollo_key")
    if not key:
        raise HTTPException(400, "Apollo API key not configured. Set it in Settings.")

    try:
        results, credits_used = await _apollo_search(
            api_key=key,
            titles=q.titles,
            industry=q.industry,
            locations=q.locations,
            company_sizes=q.company_sizes,
            target_count=q.target_count,
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))

    # Persist new leads; skip duplicates
    added = 0
    skipped = 0
    for lead_data in results:
        existing = lead_repository.get_by_email(session, lead_data["email"])
        if existing:
            skipped += 1
            continue
        lead = Lead(**{k: v for k, v in lead_data.items() if hasattr(Lead, k)})
        lead.lead_score = score_lead(lead_data)
        lead_repository.create(session, lead)
        added += 1

    return {
        "leads":        results,
        "added":        added,
        "skipped":      skipped,
        "credits_used": credits_used,
    }


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL DRAFT ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{lead_id}/preview")
async def preview_lead_email(lead_id: int, session: Session = Depends(get_db_session)):
    """Generate an AI email draft for a single lead. Stores it in draft_subject / draft_body."""
    from app.utils.prompt import build_email_prompt
    from app.utils.llm_client import generate_email
    from app.core.db import engine as db_engine

    lead = lead_repository.get(session, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")

    identity, services = _get_identity_and_services(session)
    cfg = _load_cfg(session)

    # Pre-flight: at least one provider slot has an api_key
    providers = cfg.get("providers", [])
    if not any(p.get("api_key", "").strip() for p in providers):
        raise HTTPException(400, "No LLM API key configured. Go to Settings → LLM Providers, add a provider and click Save Settings.")

    lead_data = _lead_to_dict(lead)

    # Detach from objects that depend on the session before calling the LLM
    # (services is a Sequence from session — copy it)
    services = list(services)

    sys_p, usr_p = build_email_prompt(
        lead_data, identity, services,
        cfg.get("email_style_instructions", ""),
        cfg.get("sample_email_copy", ""),
    )

    # ── LLM call (async, can take 30-90s) ────────────────────────────────
    # The injected session is NOT used across this await — SQLite doesn't
    # support concurrent writes, so holding a session open during a long
    # await blocks the DB for every other request (campaign sends, etc.).
    try:
        pkg = await generate_email(sys_p, usr_p, providers=providers)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))

    # ── Save draft in a fresh short-lived session ────────────────────────
    with Session(db_engine) as save_session:
        fresh_lead = save_session.get(Lead, lead_id)
        if fresh_lead:
            fresh_lead.draft_subject = pkg["subject"]
            fresh_lead.draft_body    = pkg["bodyHtml"]
            save_session.add(fresh_lead)
            save_session.commit()

    return {"subject": pkg["subject"], "body_html": pkg["bodyHtml"]}


@router.patch("/{lead_id}/draft")
def save_lead_draft(lead_id: int, body: dict, session: Session = Depends(get_db_session)):
    """Persist an edited email draft (subject + body HTML) for a lead."""
    lead = lead_repository.get(session, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    if "draft_subject" in body:
        lead.draft_subject = body["draft_subject"]
    if "draft_body" in body:
        lead.draft_body = body["draft_body"]
    session.add(lead)
    session.commit()
    return {"status": "saved"}


@router.get("/{lead_id}/timeline")
def get_lead_timeline(lead_id: int, session: Session = Depends(get_db_session)):
    """Return full lead profile + complete email send history for the lead."""
    from app.models.email_account import EmailAccount
    lead = lead_repository.get(session, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    campaigns = session.exec(
        select(Campaign).where(Campaign.lead_id == lead_id).order_by(Campaign.id)
    ).all()
    # Build account_id → email map so each history item can show who sent it
    account_ids = {c.account_id for c in campaigns if c.account_id}
    account_map: dict = {}
    if account_ids:
        accounts = session.exec(select(EmailAccount).where(EmailAccount.id.in_(account_ids))).all()
        account_map = {a.id: (a.display_name or a.email, a.email) for a in accounts}
    history = [{
        "id":            c.id,
        "subject":       c.subject or "",
        "sent_at":       c.sent_at or "",
        "error_message": c.error_message or "",
        "tracking_id":   c.tracking_id or "",
        "opened_at":     c.opened_at or "",
        "open_count":    c.open_count or 0,
        "sequence_step": c.sequence_step or 0,
        "account_id":    c.account_id,
        "sent_from_name": account_map.get(c.account_id, ("", ""))[0] if c.account_id else "",
        "sent_from_email": account_map.get(c.account_id, ("", ""))[1] if c.account_id else "",
        "thread_id":     c.thread_id or "",
    } for c in campaigns]
    lead_dict = _lead_to_dict(lead)
    lead_dict["last_error"] = history[-1]["error_message"] if history else ""
    lead_dict["last_sent_at"] = history[-1]["sent_at"] if history else ""
    return {"lead": lead_dict, "history": history}


@router.post("/{lead_id}/retry")
def retry_failed_lead(lead_id: int, session: Session = Depends(get_db_session)):
    """Reset a failed (or any) lead back to 'pending' so it can be re-sent."""
    lead = lead_repository.get(session, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    lead.status        = "pending"
    lead.draft_subject = ""
    lead.draft_body    = ""
    session.add(lead)
    session.commit()
    return {"status": "reset", "lead": _lead_to_dict(lead)}


@router.post("/{lead_id}/send")
async def send_single_lead(lead_id: int, session: Session = Depends(get_db_session)):
    """Send the saved draft for one lead. Generates fresh if no draft is stored."""
    from app.utils.prompt import build_email_prompt
    from app.utils.llm_client import generate_email
    from app.utils.company import wrap_email_template, render_custom_template
    from app.utils.email_engine import EmailEngine
    from app.repositories.account_repository import account_repository
    from app.core.db import engine as db_engine
    from datetime import datetime, timezone

    # ── Phase 1: read everything we need from DB (fast, no await) ────────
    lead = lead_repository.get(session, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")

    cfg = _load_cfg(session)
    lead_data = _lead_to_dict(lead)
    has_draft = bool(lead.draft_subject and lead.draft_body)
    subject       = lead.draft_subject if has_draft else ""
    body_html_raw = lead.draft_body    if has_draft else ""
    lead_email    = lead.email
    unsub_token   = lead.unsubscribe_token

    identity, services = _get_identity_and_services(session)
    services = list(services)

    accs = account_repository.get_active_accounts(session)
    if not accs:
        raise HTTPException(400, "No active email accounts configured")
    acc = accs[0]
    acc_dict = {
        "id": acc.id, "email": acc.email,
        "app_password": acc.get_decrypted_password(),
        "provider": acc.provider, "display_name": acc.display_name,
    }
    acc_email = acc.email
    acc_display = acc.display_name or acc.email.split("@")[0].title()
    acc_id = acc.id

    # ── Phase 2: generate email if no draft (async, may take 30-90s) ─────
    if not has_draft:
        providers = cfg.get("providers", [])
        if not any(p.get("api_key", "").strip() for p in providers):
            raise HTTPException(400, "No LLM API key configured. Go to Settings → LLM Providers and add your first provider.")
        sys_p, usr_p = build_email_prompt(
            lead_data, identity, services,
            cfg.get("email_style_instructions", ""),
            cfg.get("sample_email_copy", ""),
        )
        try:
            pkg = await generate_email(sys_p, usr_p, providers=providers)
        except RuntimeError as exc:
            raise HTTPException(400, str(exc))
        subject       = pkg["subject"]
        body_html_raw = pkg["bodyHtml"]

    # ── Phase 3: pre-create Campaign for tracking (fresh session) ────────
    with Session(db_engine) as s3:
        pre_campaign = Campaign(lead_id=lead_id, subject=subject, sequence_step=0)
        s3.add(pre_campaign)
        s3.commit()
        s3.refresh(pre_campaign)
        tracking_url    = f"http://127.0.0.1:8008/api/track/open/{pre_campaign.tracking_id}"
        unsubscribe_url = f"http://127.0.0.1:8008/api/unsubscribe/{unsub_token}"
        campaign_id     = pre_campaign.id

    # ── Phase 4: wrap template + send (async, may take 10-30s) ───────────
    _tpl_ctx = dict(
        inner_html=body_html_raw,
        sender_email=acc_email,
        sender_name=acc_display,
        sender_title=getattr(identity, "sender_title", "") or cfg.get("sender_title", "Executive"),
        calendly_url=getattr(identity, "calendly_url", "") or cfg.get("calendar_url", ""),
        company_name=getattr(identity, "name", "") or "",
        company_tagline=getattr(identity, "tagline", ""),
        company_logo=getattr(identity, "logo_url", ""),
        company_website=getattr(identity, "website", ""),
        offices=_offices_to_str(getattr(identity, "offices", [])),
        tracking_url=tracking_url,
        unsubscribe_url=unsubscribe_url,
    )
    custom_tpl = (cfg.get("custom_email_template") or "").strip()
    html_body = render_custom_template(custom_tpl, **_tpl_ctx) if custom_tpl else wrap_email_template(**_tpl_ctx)
    plain = re.sub(r"<[^>]+>", " ", body_html_raw).strip()

    engine = EmailEngine(
        [acc_dict],
        strategy="round_robin",
    )
    results = await engine.send_batch(
        jobs=[{"to": lead_email, "subject": subject, "html": html_body,
               "plain": plain, "lead_id": lead_id}],
        delay_seconds=0,
    )
    result = results[0]

    # ── Phase 5: update DB with result (fresh session, fast) ─────────────
    with Session(db_engine) as s5:
        lead_obj = s5.get(Lead, lead_id)
        camp = s5.get(Campaign, campaign_id)
        if lead_obj:
            lead_obj.status = "sent" if result["success"] else "failed"
            lead_obj.lead_score = score_lead(lead_data)
            s5.add(lead_obj)
        if camp:
            camp.account_id = acc_id
            if result["success"]:
                camp.sent_at = datetime.now(timezone.utc).isoformat()
            else:
                camp.error_message = result.get("error", "")
                camp.sent_at = datetime.now(timezone.utc).isoformat()
            s5.add(camp)
        s5.commit()

    if result["success"]:
        return {"status": "sent", "sent_from": result.get("sent_from", "")}
    raise HTTPException(500, result.get("error", "Send failed"))
