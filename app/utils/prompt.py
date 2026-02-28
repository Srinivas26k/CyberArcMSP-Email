"""
prompt.py — LLM prompt construction for ANY White-Labeled Identity.

Key design principles:
  • Temporal anchoring: always injects today's exact date so the AI never drifts.
  • Deep specificity: Pulls from KnowledgeBase/SrvDB dynamic contexts instead of static dictionaries.
  • Output contract: JSON only, {"subject": "...", "bodyHtml": "..."}
"""
from datetime import datetime
from typing import List
from app.models.identity import IdentityProfile, KnowledgeBase

def _build_context_pillars(services: List[KnowledgeBase]) -> str:
    """Formats the DB KnowledgeBase offerings into LLM instructions."""
    if not services:
        return "  Pillar 1 — 'General Service': We provide customized solutions to fit your needs."
        
    lines = []
    for i, srv in enumerate(services[:3]): # Max 3 for conciseness
        lines.append(f"  Pillar {i+1} — \"{srv.title}\": {srv.value_prop}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# DYNAMIC PROMPT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_email_prompt(lead: dict, identity: IdentityProfile, services: List[KnowledgeBase]) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) ready to be sent to the LLM, 
    dynamically built using the user's active database IdentityProfile.
    """
    now      = datetime.now()
    today    = now.strftime("%B %d, %Y")
    year     = now.year
    
    first    = lead.get("first_name", "there")
    role     = lead.get("role", "Executive")
    company  = lead.get("company", "your organisation")
    industry = lead.get("industry", "Technology")
    location = lead.get("location", "Global")
    employees = lead.get("employees", "")

    # Identity Profile Injects
    sender_org = identity.name or "Our Company"
    sender_pitch = identity.tagline or "Delivering premier solutions"

    system_prompt = (
        f"You are a Senior Executive at {sender_org} writing a B2B outreach email. "
        f"Your company's main value proposition is: '{sender_pitch}'.\n"
        f"TODAY IS {today} ({year}). "
        f"CRITICAL: never reference {year-1} or earlier as 'current'. "
        f"Write like a seasoned consultant — specific, confident, no generic buzzwords. "
        f"Output ONLY valid JSON, no prose outside it. "
        f'Schema: {{ "subject": "string ≤60 chars", "bodyHtml": "HTML body string — NO signature, NO sender name" }}'
    )

    named_pillars = _build_context_pillars(services)

    user_prompt = f"""
RECIPIENT
  First Name: {first}
  Full Role:  {role}
  Company:    {company}
  Industry:   {industry}
  Location:   {location}
  Employees:  {employees or 'undisclosed'}

TODAY: {today}
YOUR COMPANY ({sender_org}) SERVICE PILLARS (use these as <strong> headers — exactly these names):
{named_pillars}

NOW WRITE THE EMAIL FOR {first.upper()} AT {company.upper()}:
Rules (follow every one — no exceptions):
1. Open: <p>Hi {first},</p>
2. HOOK paragraph (2-3 sentences): Name a specific, current market pressure,
   or technology shift happening in {location} that directly affects {company}'s {industry} sector
   in {year}. Be precise. No filler.
3. PAIN paragraph (2 sentences): "As {role}, you're balancing [key initiative] with
   [key pressure]. What we see is [3 specific pain vectors] — name real problems relevant to their space."
4. Section heading: <p><strong>How {sender_org} closes the gap:</strong></p>
5. Bullet list — exactly 3 <li> items. Each MUST:
   a. Start with the EXACT pillar name from above bolded in <strong>Pillar Name:</strong>
   b. Include ONE specific action we take (name a real tool, framework, or method)
   c. Include ONE measurable result with an actual number/percentage based on the pillar's value prop.
   d. Be 2-3 sentences long. Not one generic sentence.
6. CTA: <p>Open for 15 minutes this week?</p>
7. Close: <p>Best,</p>   ← DO NOT add any name or signature. System appends it.
8. Subject line: Specific to {company} — mention city/sector/pain. Under 60 chars.
9. Use ONLY <p>, <ul>, <li>, <strong> tags. No inline styles. No <br> tags.
10. Target 220–270 words in the body.

Output JSON now:
""".strip()

    return system_prompt, user_prompt
