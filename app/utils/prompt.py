"""
prompt.py — LLM prompt construction from the user's onboarding IdentityProfile.

Produces concise, natural executive outreach emails (~280-340 words) that match
this exact structure:
  Subject → Dear [Name], → Intro (2 sentences) → Industry context (2-3 sentences)
  → "Here's how [Company] supports..." → 4-5 short service bullets → Social proof
  → CTA + calendly link → "Looking forward to connecting." → "Warm regards,"

Output contract: JSON only — {"subject": "...", "bodyHtml": "..."}
"""
from datetime import datetime
from typing import List
from app.models.identity import IdentityProfile, KnowledgeBase


def build_email_prompt(lead: dict, identity: IdentityProfile, services: List[KnowledgeBase]) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt) — both built entirely from the
    user's IdentityProfile + KnowledgeBase rows, plus the lead's real data.
    No hardcoded company content anywhere.
    """
    year  = datetime.now().year

    # ── Lead data ────────────────────────────────────────────────────────────
    first    = (lead.get("first_name") or "").strip()
    last     = (lead.get("last_name")  or "").strip()
    name     = f"{first} {last}".strip() or "there"
    greeting = first or name
    role     = lead.get("role",     "Executive")    or "Executive"
    company  = lead.get("company",  "your company") or "your company"
    industry = lead.get("industry", "Technology")   or "Technology"
    location = (lead.get("location") or "").strip()
    employees = (lead.get("employees") or "").strip()

    # ── Sender identity (from DB — what the user entered at onboarding) ──────
    sender_org      = (identity.name         or "").strip()
    sender_tagline  = (identity.tagline      or "").strip()
    sender_website  = (identity.website      or "").strip()
    sender_calendly = (identity.calendly_url or "").strip()
    # sender_name is the individual's name (e.g. "John Smith"); fall back to
    # the company name so the intro is never a literal placeholder.
    sender_name     = (identity.sender_name  or "").strip() or sender_org

    # ── Services (from DB KnowledgeBase rows) ────────────────────────────────
    svc_lines = []
    for s in services[:6]:
        title = (s.title or "").strip()
        prop  = (s.value_prop or "").strip()
        if title:
            svc_lines.append(f"  • {title} — {prop}" if prop else f"  • {title}")
    if not svc_lines:
        svc_lines = ["  • Our Services — Tailored solutions for your needs."]
    services_block = "\n".join(svc_lines)

    # ── Calendly CTA — rendered as a styled button, not a bare link ──────────
    if sender_calendly:
        cta_html = (
            f'<p style="margin:20px 0;">'
            f'<a href="{sender_calendly}" '
            f'style="display:inline-block;background:#1A56DB;color:#ffffff;'
            f'padding:12px 28px;border-radius:6px;text-decoration:none;'
            f'font-weight:600;font-size:15px;letter-spacing:0.01em;">'
            f'Book a 30-min call &rarr;</a></p>'
        )
    else:
        cta_html = "<p>Reply with a time that works for a quick 30-minute call.</p>"

    # Pre-compute strings used inside the user_prompt f-string so we don't
    # hit Python <3.12 restrictions on nested quotes inside f-string expressions.
    intro_opener = (
        f"I'm {sender_name}, reaching out from {sender_org}"
        if sender_name and sender_name != sender_org
        else f"I'm reaching out from {sender_org or 'our company'}"
    )
    sender_supports = f"{sender_org or 'we'} support{'s' if sender_org else ''}"

    # ── System prompt ────────────────────────────────────────────────────────
    system_prompt = (
        f"You are {sender_name or 'a senior executive'} at {sender_org or 'a technology company'} "
        f"writing a B2B cold outreach email. {sender_tagline}. "
        f"Write in a professional, warm, human tone — concise, no buzzwords, no hype. "
        f"Output ONLY a valid JSON object. "
        f'Schema: {{"subject": "string ≤70 chars", "bodyHtml": "HTML body — stop after Warm regards, — NO name/signature"}}'
    )

    # ── User prompt ──────────────────────────────────────────────────────────
    user_prompt = f"""Write a cold outreach email from {sender_org or "our company"} to this lead.

LEAD:
  Name:      {name}
  Title:     {role}
  Company:   {company}
  Industry:  {industry}
  Location:  {location or "N/A"}
  Employees: {employees or "N/A"}

SENDER COMPANY:
  Name:     {sender_org or "N/A"}
  Website:  {sender_website or "N/A"}
  Tagline:  {sender_tagline or "N/A"}

SERVICES OFFERED (choose the 4 most relevant to this lead's industry):
{services_block}

EXACT EMAIL STRUCTURE — follow this precisely:

Subject: "{company}'s [industry pain/opportunity] — {sender_org}" style. Max 70 chars.

Body (in order, no deviations):
1. <p>Dear {greeting},</p>

2. <p>INTRO — 2 sentences only:
   "I hope this message finds you well. {intro_opener} — [one sentence: what {sender_org or "the company"} does and
   which industries/regions it serves]."
   Use the sender name and company exactly as given — do NOT invent or change them.</p>

3. <p>CONTEXT — 2-3 sentences about ONE real challenge facing the {industry} sector in {year}.
   Reference actual industry standards, threats, or trends (e.g. regulatory requirements,
   cybersecurity threats, AI adoption pressure). Write factually — no invented stats about {company}.</p>

4. <p>Here's how {sender_supports} {industry} organizations like {company}:</p>

5. <ul> — exactly 4 <li> items. Each must be ONE sentence:
   <strong>Service Name —</strong> brief specific capability or methodology. No paragraph. No metrics unless they come from our services list above.

6. After </ul>, ONE sentence of social proof if the services list mentions any stats
   (client count, retention rate, delivery time, etc.). Skip entirely if none apply.

7. <p>CTA — 1 sentence inviting a 30-minute call to discuss their specific situation.</p>
{cta_html}

8. <p>Looking forward to connecting.</p>
   <p>Warm regards,</p>
   ← STOP HERE. No name, no title, no company, no phone. The template adds the signature.

RULES:
- Tags allowed: <p> <ul> <li> <strong> <a> only. No <div>, no inline styles.
- Total body: 250-320 words. Concise is better than thorough.
- Reference {greeting} and {company} by name naturally — not excessively.
- Output JSON only. No text outside the JSON object.

Output:""".strip()

    return system_prompt, user_prompt
