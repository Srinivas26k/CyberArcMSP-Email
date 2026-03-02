"""
sequence_service.py — Background processor for follow-up sequence enrollments.

Called every N minutes by the lifespan scheduler in main.py.
Finds all SequenceEnrollments where:
  - status == "active"
  - next_send_at <= now (UTC)

For each due enrollment it:
  1. Checks that the lead hasn't replied / unsubscribed (stops if so).
  2. Generates a follow-up email using build_email_prompt() + the step's
     instructions as the style guide.
  3. Sends the email from the first active account.
  4. Advances current_step and schedules the next step.
  5. Marks status = "completed" when all steps are exhausted.
"""
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.core.db import engine
from app.models.campaign import Campaign
from app.models.lead import Lead
from app.models.sequence import SequenceEnrollment, SequenceTemplate

logger = logging.getLogger(__name__)


def _lead_to_dict(lead: Lead) -> dict:
    return {
        "id": lead.id, "email": lead.email,
        "first_name": lead.first_name, "last_name": lead.last_name,
        "company": lead.company, "role": lead.role,
        "industry": lead.industry, "location": lead.location,
        "seniority": lead.seniority, "employees": lead.employees,
        "website": lead.website, "linkedin": lead.linkedin,
        "headline": lead.headline, "phone": lead.phone,
        "org_description": lead.org_description,
        "org_tech_stack": lead.org_tech_stack,
    }


async def process_due_enrollments() -> int:
    """Process all due sequence enrollments. Returns count of steps sent."""
    now_iso = datetime.now(timezone.utc).isoformat()
    sent_count = 0

    with Session(engine) as session:
        due = session.exec(
            select(SequenceEnrollment).where(
                SequenceEnrollment.status == "active",
                SequenceEnrollment.next_send_at <= now_iso,
            )
        ).all()

    for enrollment in due:
        try:
            sent = await _process_enrollment(enrollment.id)
            if sent:
                sent_count += 1
        except Exception as exc:
            logger.error(
                "Sequence scheduler: error on enrollment %d: %s",
                enrollment.id, exc,
            )

    if sent_count:
        logger.info("Sequence scheduler: sent %d follow-up(s)", sent_count)
    return sent_count


async def _process_enrollment(enroll_id: int) -> bool:
    """Process a single enrollment. Returns True if an email was sent."""
    from app.repositories.account_repository import account_repository
    from app.utils.llm_client import generate_email
    from app.utils.prompt import build_email_prompt
    from app.utils.company import wrap_email_template
    from app.utils.email_engine import EmailEngine

    with Session(engine) as session:
        enrollment = session.get(SequenceEnrollment, enroll_id)
        if not enrollment or enrollment.status != "active":
            return False

        lead = session.get(Lead, enrollment.lead_id)
        if not lead:
            enrollment.status = "stopped"
            session.add(enrollment)
            session.commit()
            return False

        # Auto-stop if replied or unsubscribed
        if lead.status in ("replied", "unsubscribed"):
            enrollment.status = lead.status
            session.add(enrollment)
            session.commit()
            return False

        seq = session.get(SequenceTemplate, enrollment.sequence_id)
        if not seq or not seq.is_active:
            enrollment.status = "stopped"
            session.add(enrollment)
            session.commit()
            return False

        steps = json.loads(seq.steps_json or "[]")
        if enrollment.current_step >= len(steps):
            enrollment.status = "completed"
            session.add(enrollment)
            session.commit()
            return False

        step = steps[enrollment.current_step]

        # Load LLM config + identity
        from app.models.identity import IdentityProfile, KnowledgeBase
        from app.models.setting import Setting

        identity = session.exec(select(IdentityProfile)).first()
        if not identity:
            identity = IdentityProfile(
                name="", tagline="", website="", logo_url="",
                calendly_url="", sender_title="", sender_name="",
            )
            services = []
        else:
            services = session.exec(
                select(KnowledgeBase)
                .where(KnowledgeBase.identity_id == identity.id)
                .limit(6)
            ).all()

        cfg_rows = session.exec(select(Setting)).all()
        cfg = {row.key: row.value for row in cfg_rows}

        # Parse providers
        raw_prov = cfg.pop("llm_providers", "") or ""
        providers = json.loads(raw_prov) if raw_prov else []

        if not providers:
            logger.warning("Sequence: no LLM providers configured — skipping")
            return False

        lead_data = _lead_to_dict(lead)

        # Build step-specific instructions
        step_instructions = step.get("instructions", "")
        initial_subject   = enrollment.initial_subject or lead.draft_subject or ""
        follow_up_context = (
            f"This is follow-up email #{enrollment.current_step + 1} in a sequence.\n"
            f"The initial email had subject: '{initial_subject}'.\n"
            f"Reference the previous outreach naturally without repeating it.\n"
            + (f"\nStep instructions: {step_instructions}" if step_instructions else "")
        )

        base_style   = cfg.get("email_style_instructions", "")
        merged_style = f"{base_style}\n\n{follow_up_context}".strip()

        sys_p, usr_p = build_email_prompt(
            lead_data, identity, services, merged_style, ""
        )

        # Override subject if hint provided
        subject_hint = step.get("subject_hint", "")

        accs = account_repository.get_active_accounts(session)
        if not accs:
            logger.warning("Sequence: no active email accounts — skipping enrollment %d", enroll_id)
            return False
        acc = accs[0]

    # Generate email (outside DB session to avoid long locks)
    try:
        pkg = await generate_email(sys_p, usr_p, providers=providers)
    except RuntimeError as exc:
        logger.error("Sequence: LLM error for enrollment %d: %s", enroll_id, exc)
        return False

    subject = pkg["subject"]
    if subject_hint:
        subject = f"{subject_hint} {subject}" if not subject.startswith(subject_hint) else subject

    with Session(engine) as session:
        enrollment = session.get(SequenceEnrollment, enroll_id)
        if not enrollment or enrollment.status != "active":
            return False

        identity = session.exec(select(IdentityProfile)).first()

        # Build branded HTML
        cal_url = getattr(identity, "calendly_url", "") if identity else ""
        org_name = getattr(identity, "name", "") if identity else ""
        org_tagline = getattr(identity, "tagline", "") if identity else ""
        org_logo = getattr(identity, "logo_url", "") if identity else ""
        org_web = getattr(identity, "website", "") if identity else ""

        # Build unsubscribe URL
        lead = session.get(Lead, enrollment.lead_id)
        unsubscribe_url = f"http://127.0.0.1:8008/api/unsubscribe/{lead.unsubscribe_token}"

        # Pre-create Campaign to get tracking_id
        campaign = Campaign(
            lead_id=enrollment.lead_id,
            subject=subject,
            sequence_step=enrollment.current_step + 1,
        )
        session.add(campaign)
        session.commit()
        session.refresh(campaign)

        tracking_url = f"http://127.0.0.1:8008/api/track/open/{campaign.tracking_id}"
        html_body = wrap_email_template(
            inner_html=pkg["bodyHtml"],
            sender_email=acc["email"] if isinstance(acc, dict) else acc.email,
            sender_name=acc.get("display_name", "") if isinstance(acc, dict) else (acc.display_name or ""),
            sender_title=getattr(identity, "sender_title", "Executive") if identity else "Executive",
            calendly_url=cal_url,
            company_name=org_name,
            company_tagline=org_tagline,
            company_logo=org_logo,
            company_website=org_web,
            tracking_url=tracking_url,
            unsubscribe_url=unsubscribe_url,
        )
        plain = re.sub(r"<[^>]+>", " ", pkg["bodyHtml"]).strip()

    engine_inst = EmailEngine(
        [{"id": acc.id, "email": acc.email,
          "app_password": acc.get_decrypted_password(),
          "provider": acc.provider, "display_name": acc.display_name}],
        strategy="round_robin",
    )
    results = await engine_inst.send_batch(
        jobs=[{"to": lead.email, "subject": subject,
               "html": html_body, "plain": plain, "lead_id": lead.id}],
        delay_seconds=0,
    )
    result = results[0]

    with Session(engine) as session:
        enrollment = session.get(SequenceEnrollment, enroll_id)
        campaign_obj = session.get(Campaign, campaign.id)

        if result["success"]:
            campaign_obj.sent_at = datetime.now(timezone.utc).isoformat()
            enrollment.last_sent_at = datetime.now(timezone.utc).isoformat()
            enrollment.current_step += 1

            steps_reload = json.loads(
                session.get(SequenceTemplate, enrollment.sequence_id).steps_json or "[]"
            )
            if enrollment.current_step >= len(steps_reload):
                enrollment.status = "completed"
            else:
                next_step = steps_reload[enrollment.current_step]
                delay = next_step.get("delay_days", 3)
                next_dt = datetime.now(timezone.utc) + timedelta(days=delay)
                enrollment.next_send_at = next_dt.isoformat()
        else:
            campaign_obj.error_message = result.get("error", "Send failed")

        session.add(campaign_obj)
        session.add(enrollment)
        session.commit()

    return result["success"]
