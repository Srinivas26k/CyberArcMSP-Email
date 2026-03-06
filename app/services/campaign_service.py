import asyncio
from datetime import datetime, timezone
from sqlmodel import Session
from app.core.db import engine
from app.models.lead import Lead
from app.models.campaign import Campaign
from app.repositories.account_repository import account_repository
from app.utils.email_engine import EmailEngine
from app.utils.llm_client import generate_email
from app.utils.prompt import build_email_prompt
from app.utils.company import wrap_email_template, render_custom_template
from app.utils.payload_sanitizer import PayloadSanitizer, PayloadSanitizationError, PersonalizationError
from app.utils.scoring import score_lead
import re
import random

import logging
logger = logging.getLogger(__name__)

class CampaignService:
    @staticmethod
    def _html_to_plain(html: str) -> str:
        return re.sub(r"<[^>]+>", " ", html).replace("  ", " ").strip()

    @staticmethod
    def _lead_to_dict(lead: Lead) -> dict:
        return {
            "id": lead.id,
            "email": lead.email,
            "first_name": lead.first_name,
            "last_name": lead.last_name,
            "company": lead.company,
            "role": lead.role,
            "industry": lead.industry,
            "location": lead.location,
            "seniority": lead.seniority,
            "employees": lead.employees,
            "website": lead.website,
            "linkedin": lead.linkedin,
            "status": lead.status,
            "created_at": lead.created_at
        }

    # Pass in the state callback to abstract SSE broadcasts
    @staticmethod
    async def run_campaign_batch(lead_ids: list[int], delay: int, account_ids: list[int] | None, cfg: dict, broadcast_cb, running_flag_check):
        await broadcast_cb("stat", {"message": f"Campaign started for {len(lead_ids)} leads"})
        
        try:
            with Session(engine) as session:
                accs = account_repository.get_active_accounts(session)
                if account_ids:
                    accs = [a for a in accs if a.id in account_ids]
                    
                account_list = [{"id": a.id, "email": a.email, "app_password": a.get_decrypted_password(),
                                  "provider": a.provider, "display_name": a.display_name} for a in accs]
                email_to_account_id = {a["email"]: a["id"] for a in account_list}
                email_engine = EmailEngine(
                    account_list,
                    strategy=cfg.get("send_strategy", "round_robin"),
                    batch_size=int(cfg.get("batch_size", 5)),
                )

            for i, lead_id in enumerate(lead_ids, 1):
                if not running_flag_check():
                    break

                # ── Adaptive delay BEFORE drafting the next lead ─────────
                # (skip delay before the very first lead)
                if i > 1:
                    actual_delay = random.randint(60, 120) if delay <= 0 else delay
                    await broadcast_cb("stat", {"message": f"Waiting {actual_delay}s before next send ({i-1}/{len(lead_ids)} done)..."})
                    for _ in range(actual_delay):
                        if not running_flag_check():
                            break
                        await asyncio.sleep(1)
                    if not running_flag_check():
                        break

                await broadcast_cb("stat", {"message": f"Drafting email {i} of {len(lead_ids)}..."})

                try:
                    with Session(engine) as session:
                        lead = session.get(Lead, lead_id)
                        if not lead or lead.status != "pending":
                            logger.info(f"Skipping lead {lead_id}: status={getattr(lead, 'status', 'not found')}")
                            continue
                        lead.status = "drafting"
                        session.add(lead)
                        session.commit()

                    await broadcast_cb("lead_update", {"lead_id": lead_id, "status": "drafting"})

                    from app.models.identity import IdentityProfile, KnowledgeBase
                    from sqlmodel import select
                    
                    with Session(engine) as session:
                        lead = session.get(Lead, lead_id)
                        if lead is None:
                            raise RuntimeError(f"Lead {lead_id} not found in DB")
                        lead_data = CampaignService._lead_to_dict(lead)

                        # Load dynamic Identity from DB (set during onboarding)
                        identity = session.exec(select(IdentityProfile)).first()
                        if not identity:
                            # Onboarding not completed — use empty identity, LLM uses generic language
                            identity = IdentityProfile(
                                name="", tagline="", website="", logo_url="",
                                calendly_url="", sender_title="", sender_name=""
                            )
                            services = []
                        else:
                            services = session.exec(
                                select(KnowledgeBase)
                                .where(KnowledgeBase.identity_id == identity.id)
                                .limit(6)
                            ).all()

                    # Dynamic prompt generation
                    _style = cfg.get("email_style_instructions", "")
                    _sample = cfg.get("sample_email_copy", "")
                    sys_p_temp, usr_p_temp = build_email_prompt(lead_data, identity, list(services), _style, _sample)
                    sanitized_lead_data = PayloadSanitizer.truncate_context(lead_data, usr_p_temp, max_chars=4000)
                    sys_p, usr_p = build_email_prompt(sanitized_lead_data, identity, list(services), _style, _sample)
                    
                    pkg = None
                    for attempt in range(2):
                        pkg = await generate_email(
                            sys_p, usr_p,
                            providers=cfg.get("providers", []),
                        )
                        
                        temp_plain = CampaignService._html_to_plain(pkg["bodyHtml"])
                        
                        spam_matches = PayloadSanitizer.has_spam_keywords(temp_plain)
                        if spam_matches:
                            raise PayloadSanitizationError(f"422 Unprocessable LLM Output: Spam keywords detected: {', '.join(spam_matches)}")
                            
                        is_personalized = PayloadSanitizer.verify_personalization(
                            temp_plain, 
                            lead_data.get("first_name", ""), 
                            lead_data.get("company", "")
                        )
                        
                        if is_personalized:
                            break
                        if attempt == 1:
                            raise PersonalizationError("422 Unprocessable Output: LLM failed to personalize the email with first name or company.")
                    
                    assert pkg is not None, "Email generation produced no output"

                    # Fetch branding from Identity with fallbacks
                    sender_title = getattr(identity, 'sender_title', "Executive") or cfg.get("sender_title", "Executive")
                    calendar = getattr(identity, 'calendly_url', "") or cfg.get("calendar_url", "")
                    org_name = getattr(identity, 'name', "Company")
                    org_tagline = getattr(identity, 'tagline', "")
                    org_logo = getattr(identity, 'logo_url', "")
                    org_web = getattr(identity, 'website', "")
                    offices_raw = getattr(identity, 'offices', [])
                    # offices can be List[dict], List[str], or str (legacy) — normalise to str
                    if isinstance(offices_raw, list):
                        offices_str = " • ".join(
                            (o.get("city") or o.get("name") or str(o)) if isinstance(o, dict) else str(o)
                            for o in offices_raw if o
                        ) if offices_raw else ""
                    else:
                        offices_str = str(offices_raw)

                    # Pre-create Campaign to get tracking_id before send
                    with Session(engine) as session:
                        lead_for_unsub = session.get(Lead, lead_id)
                        pre_campaign = Campaign(
                            lead_id=lead_id,
                            subject=pkg["subject"],
                            sequence_step=0,
                        )
                        session.add(pre_campaign)
                        session.commit()
                        session.refresh(pre_campaign)
                        tracking_url   = f"http://127.0.0.1:8008/api/track/open/{pre_campaign.tracking_id}"
                        unsubscribe_url = (
                            f"http://127.0.0.1:8008/api/unsubscribe/{lead_for_unsub.unsubscribe_token}"
                            if lead_for_unsub else ""
                        )
                        campaign_id = pre_campaign.id

                    # Build branded HTML wrapper — use custom template if configured
                    _tpl_ctx = dict(
                        inner_html=pkg["bodyHtml"],
                        sender_email="{{SENDER_EMAIL}}",
                        sender_name="{{SENDER_NAME}}",
                        sender_title=sender_title,
                        calendly_url=calendar,
                        company_name=org_name,
                        company_tagline=org_tagline,
                        company_logo=org_logo,
                        company_website=org_web,
                        offices=offices_str,
                        tracking_url=tracking_url,
                        unsubscribe_url=unsubscribe_url,
                    )
                    custom_tpl = (cfg.get("custom_email_template") or "").strip()
                    if custom_tpl:
                        html_body = render_custom_template(custom_tpl, **_tpl_ctx)
                    else:
                        html_body = wrap_email_template(**_tpl_ctx)
                    plain = CampaignService._html_to_plain(pkg["bodyHtml"])

                    results = await email_engine.send_batch(
                        jobs=[{"to": lead_data["email"], "subject": pkg["subject"],
                               "html": html_body, "plain": plain, "lead_id": lead_id}],
                        delay_seconds=0,
                    )
                    result = results[0]
                    sent_from_email = result.get("sent_from", "")
                    account_id_for_camp = email_to_account_id.get(sent_from_email)

                    with Session(engine) as session:
                        lead = session.get(Lead, lead_id)
                        camp = session.get(Campaign, campaign_id)
                        if lead is None:
                            raise RuntimeError(f"Lead {lead_id} disappeared from DB after send")
                        if result["success"]:
                            lead.status = "sent"
                            lead.lead_score = score_lead(lead_data)
                            lead.draft_subject = pkg["subject"]
                            lead.draft_body = pkg["bodyHtml"]
                            if camp:
                                camp.sent_at = datetime.now(timezone.utc).isoformat()
                                if account_id_for_camp:
                                    camp.account_id = account_id_for_camp
                        else:
                            lead.status = "failed"
                            if camp:
                                camp.error_message = result.get("error", "Unknown error")
                                camp.sent_at = datetime.now(timezone.utc).isoformat()
                        session.add(lead)
                        if camp:
                            session.add(camp)
                        session.commit()

                    status = "sent" if result["success"] else "failed"
                    await broadcast_cb("lead_update", {"lead_id": lead_id, "status": status,
                                                      "sent_from": result.get("sent_from", ""),
                                                      "subject": pkg.get("subject", "")})

                except Exception as exc:
                    logger.error(f"Campaign error on lead {lead_id}: {exc}")
                    with Session(engine) as session:
                        lead = session.get(Lead, lead_id)
                        if lead:
                            lead.status = "failed"
                            session.add(lead)
                            session.commit()
                    await broadcast_cb("lead_update", {"lead_id": lead_id, "status": "failed",
                                                      "error": str(exc)[:200]})

        finally:
            await broadcast_cb("campaign_done", {"message": "Campaign finished"})
            await broadcast_cb("stat", {"refresh": True})
            logger.info("Campaign complete")

campaign_service = CampaignService()
