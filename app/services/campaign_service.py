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
from app.utils.company import wrap_email_template
from app.utils.payload_sanitizer import PayloadSanitizer, PayloadSanitizationError, PersonalizationError
import re

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
                    
                email_engine = EmailEngine(
                    [{"id": a.id, "email": a.email, "app_password": a.app_password,
                      "provider": a.provider, "display_name": a.display_name} for a in accs],
                    strategy=cfg.get("send_strategy", "round_robin"),
                    batch_size=int(cfg.get("batch_size", 5)),
                )

            for lead_id in lead_ids:
                if not running_flag_check():
                    break

                with Session(engine) as session:
                    lead = session.get(Lead, lead_id)
                    if not lead or lead.status != "pending":
                        continue
                    lead.status = "drafting"
                    session.add(lead)
                    session.commit()
                
                await broadcast_cb("lead_update", {"lead_id": lead_id, "status": "drafting"})

                try:
                    from app.models.identity import IdentityProfile, KnowledgeBase
                    from sqlmodel import select
                    
                    with Session(engine) as session:
                        lead = session.get(Lead, lead_id)
                        lead_data = CampaignService._lead_to_dict(lead)
                        
                        # Load dynamic Identity
                        identity = session.exec(select(IdentityProfile)).first()
                        if not identity:
                            identity = IdentityProfile(name="Generic Corp", tagline="Solutions")
                            
                        # Load Contextual Services (later we will use SrvDB semantic search here, for now grab top 3)
                        services = session.exec(select(KnowledgeBase).where(KnowledgeBase.identity_id == identity.id).limit(3)).all()

                    # Dynamic prompt generation
                    sys_p_temp, usr_p_temp = build_email_prompt(lead_data, identity, services)
                    sanitized_lead_data = PayloadSanitizer.truncate_context(lead_data, usr_p_temp, max_chars=4000)
                    sys_p, usr_p = build_email_prompt(sanitized_lead_data, identity, services)
                    
                    pkg = None
                    for attempt in range(2):
                        pkg = await generate_email(
                            sys_p, usr_p,
                            groq_key=cfg.get("groq_key", ""),
                            openrouter_key=cfg.get("openrouter_key", ""),
                            preferred_provider=cfg.get("llm_provider", "groq"),
                            openrouter_model=cfg.get("openrouter_model") or None,
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
                    
                    # Fetch branding from Identity with fallbacks
                    sender_title = getattr(identity, 'sender_title', "Executive") or cfg.get("sender_title", "Executive")
                    calendar = getattr(identity, 'calendly_url', "") or cfg.get("calendar_url", "")
                    org_name = getattr(identity, 'name', "Company")
                    org_tagline = getattr(identity, 'tagline', "")
                    org_logo = getattr(identity, 'logo_url', "")
                    org_web = getattr(identity, 'website', "")
                    offices_list = getattr(identity, 'offices', [])
                    
                    # Replace static template wrapper with dynamic injects
                    # NOTE: wrap_email_template still exists in company.py which we will delete shortly.
                    # Instead, we will generate the raw HTML straight here or from a DB template record.
                    
                    html_body = wrap_email_template(
                        pkg["bodyHtml"],
                        sender_email="{{SENDER_EMAIL}}",
                        sender_name="{{SENDER_NAME}}",
                        sender_title=sender_title,
                        calendly_url=calendar,
                        company_name=org_name,
                        company_tagline=org_tagline,
                        company_logo=org_logo,
                        company_website=org_web,
                        offices=offices_list,
                    )
                    plain = CampaignService._html_to_plain(pkg["bodyHtml"])

                    results = await email_engine.send_batch(
                        jobs=[{"to": lead_data["email"], "subject": pkg["subject"],
                               "html": html_body, "plain": plain, "lead_id": lead_id}],
                        delay_seconds=0,
                    )
                    result = results[0]

                    with Session(engine) as session:
                        lead = session.get(Lead, lead_id)
                        if result["success"]:
                            lead.status = "sent"
                            campaign = Campaign(
                                lead_id=lead_id,
                                subject=pkg["subject"],
                                sent_at=datetime.now(timezone.utc).isoformat(),
                            )
                            session.add(campaign)
                        else:
                            lead.status = "failed"
                            campaign = Campaign(
                                lead_id=lead_id,
                                error_message=result.get("error", "Unknown error"),
                                sent_at=datetime.now(timezone.utc).isoformat(),
                            )
                            session.add(campaign)
                        session.add(lead)
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

                await asyncio.sleep(delay)

        finally:
            await broadcast_cb("campaign_done", {"message": "Campaign finished"})
            await broadcast_cb("stat", {"refresh": True})
            logger.info("Campaign complete")

campaign_service = CampaignService()
