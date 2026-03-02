"""
prompt.py -- LLM prompt construction from the user's onboarding IdentityProfile.

Design philosophy:
  - The user's style_instructions and sample_email_copy are THE authority.
  - When style is provided it fully controls tone, length, structure, and voice.
  - When no style is provided the LLM writes naturally based on the sender
    identity and lead context -- no rigid structure is imposed.
  - Only hard constraints are: valid HTML subset, no invented stats, JSON output.

Output contract: JSON only -- {"subject": "...", "bodyHtml": "..."}
"""
from typing import List
from app.models.identity import IdentityProfile, KnowledgeBase


def build_email_prompt(
    lead: dict,
    identity: IdentityProfile,
    services: List[KnowledgeBase],
    style_instructions: str = "",
    sample_email_copy: str = "",
) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt) built entirely from DB data + lead.

    style_instructions: free-text writing guide set by the user (tone, length,
                        structure, voice, etc.).  When provided it is the
                        highest-priority directive -- the LLM must follow it
                        over any default behaviour.
    sample_email_copy:  a real email the user likes.  LLM mirrors its rhythm,
                        length and voice (not its content).
    """

    # -- Lead data -------------------------------------------------------------
    first     = (lead.get("first_name") or "").strip()
    last      = (lead.get("last_name")  or "").strip()
    name      = f"{first} {last}".strip() or "there"
    greeting  = first or name
    role      = lead.get("role",      "Executive")    or "Executive"
    company   = lead.get("company",   "your company") or "your company"
    industry  = lead.get("industry",  "Technology")   or "Technology"
    location  = (lead.get("location")  or "").strip()
    employees = (lead.get("employees") or "").strip()

    # Qualitative size label -- never quote raw headcount
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

    # -- Sender identity -------------------------------------------------------
    sender_org     = (identity.name        or "").strip()
    sender_tagline = (identity.tagline     or "").strip()
    sender_website = (identity.website     or "").strip()
    sender_name    = (identity.sender_name or "").strip() or sender_org

    # -- Services --------------------------------------------------------------
    valid_svcs = [s for s in services if (s.title or "").strip()]
    svc_lines  = []
    for s in valid_svcs:
        title = s.title.strip()
        prop  = (s.value_prop or "").strip()
        svc_lines.append(f"  - {title}: {prop}" if prop else f"  - {title}")
    if not svc_lines:
        svc_lines = ["  - Our Services: Tailored solutions for your needs."]
    services_block = "\n".join(svc_lines)

    # -- System prompt -- sets persona + writing style -------------------------
    _default_style = (
        "Write in a professional, warm, executive tone. "
        "Be story-driven and empathetic. No buzzwords, no invented statistics."
    )
    _style_directive = style_instructions.strip() if style_instructions.strip() else _default_style

    system_prompt = (
        "You are " + (sender_name or "a senior executive") + " at "
        + (sender_org or "a company") + " writing a personalized cold outreach email."
        + (" " + sender_tagline + "." if sender_tagline else "")
        + "\n\n"
        + _style_directive
        + "\n\n"
        + 'Output ONLY a valid JSON object: {"subject": "string", "bodyHtml": "string"}'
    )

    # -- User prompt -----------------------------------------------------------

    # Style block -- injected first so it governs everything that follows
    _style_block = ""
    if style_instructions.strip():
        _style_block = (
            "WRITING STYLE (your highest priority -- override all defaults below):\n"
            "---\n"
            + style_instructions.strip() + "\n"
            "---\n\n"
        )
    if sample_email_copy.strip():
        _style_block += (
            "STYLE REFERENCE (mirror this email's rhythm, voice, and length -- NOT its content):\n"
            "---\n"
            + sample_email_copy.strip() + "\n"
            "---\n\n"
        )

    user_prompt = (
        _style_block
        + "Write a personalized cold outreach email from "
        + (sender_org or "our company") + " to the following prospect.\n\n"

        + "PROSPECT:\n"
        + "  Name:     " + name + "\n"
        + "  Title:    " + role + "\n"
        + "  Company:  " + company + "\n"
        + "  Industry: " + industry + "\n"
        + "  Location: " + (location or "N/A") + "\n"
        + "  Size:     " + (employees or "N/A")
        + "  (refer to them as a '" + size_label + "' -- never quote the raw number)\n\n"

        + "SENDER:\n"
        + "  Name:     " + (sender_name or "N/A") + "\n"
        + "  Company:  " + (sender_org or "N/A") + "\n"
        + "  Website:  " + (sender_website or "N/A") + "\n"
        + "  Tagline:  " + (sender_tagline or "N/A") + "\n\n"

        + "SERVICES (weave in the most relevant ones for the " + industry + " space):\n"
        + services_block + "\n\n"

        + "HARD CONSTRAINTS (always apply regardless of style):\n"
        + "- Subject line: a compelling hook specific to " + company + " -- max 70 chars\n"
        + "- Address " + greeting + " by first name\n"
        + "- Reference " + company + "'s situation in the " + industry + " space naturally\n"
        + "- Do NOT invent statistics or facts about " + company + "\n"
        + "- Do NOT include a booking link or button (it is added automatically)\n"
        + "- End with 'Looking forward to connecting.' then 'Warm regards,' -- stop there\n"
        + "  (name, title, and contact details are rendered separately by the app)\n"
        + "- Allowed HTML tags: <p> <ul> <li> <strong> -- no <div> <br> <a> <h1-h6>\n"
        + "- Output JSON ONLY -- no markdown fences, no text outside the JSON\n\n"

        + "Output:"
    )

    return system_prompt, user_prompt
