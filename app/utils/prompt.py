"""
prompt.py — LLM prompt construction from the user's onboarding IdentityProfile.

Email structure (matches the reference J&J / Healthcare templates):
  Subject
  Dear [Name],
  1. Intro       — 2 sentences: who you are + what the company does / where it serves
  2. Company para — 2-3 sentences: narrative about the LEAD'S company/situation
                    (no regulatory stats, no specific numbers — story-first)
                    Ends with: "I believe [sender_org] can offer meaningful value..."
  3. Transition  — "Here's how [sender] supports [industry] like [company]:"
  4. 4-5 bullets — primary services (one sentence each)
  5. Also-offers — "Beyond these, we also provide …" (extra service titles)
  6. Social proof — 1 sentence if KnowledgeBase entries mention verifiable stats
  7. CTA sentence — personal invitation for a 30-min call
  8. Closing ("Looking forward to connecting." / "Warm regards,")
  NOTE: The Calendly booking button is injected by wrap_email_template(), not here.
  9. "Looking forward to connecting." / "Warm regards,"   ← STOP

Output contract: JSON only — {"subject": "...", "bodyHtml": "..."}
"""
from datetime import datetime
from typing import List
from app.models.identity import IdentityProfile, KnowledgeBase


def build_email_prompt(
    lead: dict,
    identity: IdentityProfile,
    services: List[KnowledgeBase],
) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt) built entirely from DB data + lead."""

    year = datetime.now().year

    # ── Lead data ─────────────────────────────────────────────────────────────
    first     = (lead.get("first_name") or "").strip()
    last      = (lead.get("last_name")  or "").strip()
    name      = f"{first} {last}".strip() or "there"
    greeting  = first or name
    role      = lead.get("role",      "Executive")    or "Executive"
    company   = lead.get("company",   "your company") or "your company"
    industry  = lead.get("industry",  "Technology")   or "Technology"
    location  = (lead.get("location")  or "").strip()
    employees = (lead.get("employees") or "").strip()

    # Size descriptor for the narrative paragraph (qualitative, never the raw number)
    size_label = "organization"
    if employees:
        try:
            n = int(str(employees).replace(",", "").split("-")[0].strip())
            if n >= 10_000:
                size_label = "global enterprise"
            elif n >= 1_000:
                size_label = "large organization"
            elif n >= 200:
                size_label = "growing organization"
        except ValueError:
            pass

    # ── Sender identity ───────────────────────────────────────────────────────
    sender_org      = (identity.name         or "").strip()
    sender_tagline  = (identity.tagline      or "").strip()
    sender_website  = (identity.website      or "").strip()
    sender_calendly = (identity.calendly_url or "").strip()
    # Individual sender name; falls back to company name so intro is never blank
    sender_name     = (identity.sender_name  or "").strip() or sender_org

    # ── Services — split into featured bullets + "we also provide" extras ─────
    valid_svcs = [s for s in services if (s.title or "").strip()]
    primary    = valid_svcs[:3]   # exactly 3 featured bullets
    extra      = valid_svcs[3:]   # remaining → "we also provide" line

    svc_lines = []
    for s in primary:
        title = s.title.strip()
        prop  = (s.value_prop or "").strip()
        svc_lines.append(f"  * {title} -- {prop}" if prop else f"  * {title}")
    if not svc_lines:
        svc_lines = ["  * Our Services -- Tailored solutions for your needs."]
    services_block = "\n".join(svc_lines)

    extra_titles = [s.title.strip() for s in extra if s.title.strip()]
    also_offers  = ", ".join(extra_titles) if extra_titles else ""

    # Pre-compute strings that appear inside the f-string to avoid nested-quote
    # issues on Python < 3.12.
    intro_opener = (
        "I'm " + sender_name + ", reaching out from " + sender_org
        if sender_name and sender_name != sender_org
        else "I'm reaching out from " + (sender_org or "our company")
    )
    sender_supports = (sender_org or "we") + (" supports" if sender_org else " support")

    also_offers_instruction = (
        "Include this paragraph after the </ul>:\n"
        '  <p>Beyond these, we also provide ' + also_offers + '.</p>'
        if also_offers
        else "SKIP — no additional services to list. Do NOT add any 'also provide' paragraph."
    )

    # ── System prompt ─────────────────────────────────────────────────────────
    system_prompt = (
        "You are " + (sender_name or "a senior executive") + " at "
        + (sender_org or "a technology company") + " writing a B2B cold outreach email. "
        + sender_tagline + ". "
        "Write in a professional, warm, executive tone — story-driven, no buzzwords, "
        "no invented statistics. "
        'Output ONLY a valid JSON object: {"subject": "string", "bodyHtml": "string"}'
    )

    # ── User prompt ───────────────────────────────────────────────────────────
    user_prompt = (
        "Write a cold outreach email from " + (sender_org or "our company") + " to:\n\n"
        "LEAD:\n"
        "  Name:      " + name + "\n"
        "  Title:     " + role + "\n"
        "  Company:   " + company + "\n"
        "  Industry:  " + industry + "\n"
        "  Location:  " + (location or "N/A") + "\n"
        "  Employees: " + (employees or "N/A") + "  --> describe as a '" + size_label + "' (never quote the raw number)\n\n"
        "SENDER:\n"
        "  Name:     " + (sender_name or "N/A") + "\n"
        "  Company:  " + (sender_org or "N/A") + "\n"
        "  Website:  " + (sender_website or "N/A") + "\n"
        "  Tagline:  " + (sender_tagline or "N/A") + "\n\n"
        "SERVICES (pick 4-5 most relevant to " + industry + "):\n"
        + services_block + "\n\n"
        "════════════════════════════════════\n"
        "EXACT STRUCTURE — follow in order:\n"
        "════════════════════════════════════\n\n"
        "Subject line:\n"
        '  Pattern: "[hook specific to ' + company + '] — ' + (sender_org or "us") + '"\n'
        "  Max 70 chars.\n\n"
        "1. <p>Dear " + greeting + ",</p>\n\n"
        "2. <p>INTRO — exactly 2 sentences:\n"
        '   S1: "I hope this message finds you well."\n'
        '   S2: "' + intro_opener + " — [one clause: what " + (sender_org or "we") + " does"
        " and which sectors/regions we serve].\"\n"
        "   Keep sender name and company exactly as given.</p>\n\n"
        "3. <p>COMPANY NARRATIVE — exactly 1 sentence. RULES:\n"
        "   - Write ONE sentence only that names the lead's situation in the " + industry + " space.\n"
        "   - Use '" + company + "' at most ONCE — in this sentence.\n"
        "   - Describe ONE real challenge or dynamic they face (story language only —\n"
        "     no regulatory names, no statistics, no years, no law citations).\n"
        "   - Do NOT add a second sentence about '" + (sender_org or "we") + "' — that belief\n"
        "     line is gone. The transition in step 4 carries that forward.\n"
        "   - Do NOT invent facts about " + company + ".\n"
        "   Example pattern: 'As a " + size_label + " in " + industry + ", " + company + "\n"
        "     [one clause about their challenge].'\n"
        "   Another pattern: 'Given " + company + "'s [focus area], [one clause about the\n"
        "     pressure they navigate].'</p>\n\n"
        "4. <p>Here's how " + sender_supports + " " + industry + " organizations like " + company + ":</p>\n\n"
        "5. <ul> — exactly 3 <li> from the SERVICES list above.\n"
        "   Format: <strong>Service Title —</strong> one-sentence benefit.\n"
        "   Use only services from the list. Do not invent new ones.\n\n"
        "6. ALSO-PROVIDE PARAGRAPH:\n"
        + also_offers_instruction + "\n\n"
        "7. SOCIAL PROOF — include ONLY if the SERVICES list contains a verifiable stat\n"
        "   (client count, retention rate, uptime %). Write 1 sentence using only those\n"
        "   exact stats. Skip entirely if no stats appear in the services list.\n\n"
        "8. <p>PERSONAL CTA — 1 sentence: invite " + greeting + " to a 30-minute\n"
        "   conversation to understand " + company + "'s current situation and explore\n"
        "   how " + (sender_org or "we") + " can help.\n"
        '   Use warm executive language: "I would welcome…" or "I\'d love to…"\n'
        '   Write this as a plain <p> only — do NOT output any <a> button.\n'
        '   A styled booking button is appended automatically by the mailer.\n\n'
        "9. <p>Looking forward to connecting.</p>\n"
        "   <p>Warm regards,</p>\n"
        "   STOP HERE. No name, title, email, phone, or website after this.\n"
        "   The application renders the signature block separately.\n\n"
        "════════════════════════\n"
        "RULES\n"
        "════════════════════════\n"
        "- Allowed HTML: <p> <ul> <li> <strong> only. No <div>, no <br>, no <a> buttons.\n"
        "- Total body: 280-360 words.\n"
        "- Reference " + greeting + " and " + company + " naturally — not in every sentence.\n"
        "- Output JSON ONLY. No markdown fences, no explanation outside the JSON.\n\n"
        "Output:"
    )

    return system_prompt, user_prompt
