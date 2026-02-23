"""
prompt.py — LLM prompt construction for SRV AI Email Outreach.

Key design principles:
  • Temporal anchoring: always injects today's exact date so the AI never drifts to 2024.
  • 50% Technology / 50% Risk & Compliance framing — hardcoded in the mission block.
  • Smart context: maps industry + role → best-fit services + compliance angle.
  • Output contract: JSON only, {"subject": "...", "bodyHtml": "..."}
"""
import re
from datetime import datetime
from company import SERVICE_PORTFOLIO


# ─────────────────────────────────────────────────────────────────────────────
# INDUSTRY → CONTEXT MAPPING
# ─────────────────────────────────────────────────────────────────────────────

_INDUSTRY_CONTEXTS = [
    (r"oil|gas|petro|energy|power|utilities",  "energy",        "Critical OT/IT convergence risks in energy infrastructure",       "NERC CIP, HSE & IEC 62443 compliance",              ["c_level_advisory", "cybersecurity"]),
    (r"bank|financ|invest|capital|bfsi|fund",   "bfsi",          "High-frequency trading resilience & cross-border data integrity", "SEC, GLBA, PCI DSS 4.0 & SWIFT security frameworks", ["cybersecurity", "audit_compliance"]),
    (r"health|medic|pharma|biotech|hospital",   "healthcare",    "Patient-data integrity & medical-IoT vulnerabilities",            "HIPAA, HITECH & PHI data governance",               ["cybersecurity", "audit_compliance"]),
    (r"manufact|factory|steel|industr|automat", "manufacturing", "Smart-factory SCADA hardening & IP-theft prevention",            "IEC 62443, NIST CSF & supply-chain controls",        ["ai_toolkit", "cloud_devsecops"]),
    (r"saas|software|tech|startup|platform",    "saas",          "Rapid scaling vs accumulating security debt",                    "SOC 2 Type II, data sovereignty & GDPR",             ["saas_services", "aiml_services"]),
    (r"retail|ecom|consumer|fmcg",              "retail",        "Omnichannel fraud vectors & POS system exposure",               "PCI DSS & consumer data regulations",                ["cybersecurity", "audit_compliance"]),
    (r"telecom|telco|isp|network",              "telecom",       "Network infrastructure integrity & insider threat risks",        "FCC, NIS2 Directive & carrier-grade security",       ["cybersecurity", "cloud_devsecops"]),
    (r"edu|university|school|academy",          "education",     "Research IP protection & ransomware in academic networks",       "FERPA & NIST Cybersecurity Framework",               ["cybersecurity", "corporate_training"]),
    (r"gov|government|public|minister",         "government",    "Nation-state threats to critical national infrastructure",       "FISMA, Cyber Essentials & FedRAMP",                  ["cybersecurity", "audit_compliance"]),
]

_ROLE_OVERRIDES = [
    (r"cfo|chief financial|treasurer",                ["c_level_advisory", "audit_compliance"]),
    (r"ceo|chief executive|md |president|founder",    ["c_level_advisory", "cybersecurity"]),
    (r"ciso|chief information security|vp security",  ["cybersecurity", "audit_compliance", "ai_toolkit"]),
    (r"cto|chief technology|vp engineering",          ["cloud_devsecops", "aiml_services"]),
    (r"cio|chief information|head it|director it",    ["cloud_devsecops", "audit_compliance"]),
    (r"risk|compliance|audit|legal|grc",              ["audit_compliance", "c_level_advisory"]),
    (r"hr|people|talent|culture",                     ["strategic_staffing", "corporate_training"]),
]


def get_smart_context(lead: dict) -> dict:
    """
    Analyses the lead's company, industry, and role to select the most
    relevant service pillars and compliance angle.
    Returns a context dict consumed by build_email_prompt().
    """
    text = f"{lead.get('company', '')} {lead.get('industry', '')}".lower()
    role = lead.get("role", "").lower()

    # Default context
    ctx = {
        "key":           "technology",
        "hook":          "Digital transformation pressure and evolving cyber-threat landscape",
        "risk":          "General compliance & data governance obligations",
        "service_keys":  ["c_level_advisory", "cybersecurity"],
    }

    # Industry match (first wins)
    for pattern, key, hook, risk, services in _INDUSTRY_CONTEXTS:
        if re.search(pattern, text):
            ctx.update(key=key, hook=hook, risk=risk, service_keys=services)
            break

    # Role-level override (more specific)
    for pattern, services in _ROLE_OVERRIDES:
        if re.search(pattern, role):
            ctx["service_keys"] = services
            break

    # Build human-readable service bullet list
    ctx["services_text"] = "\n".join(
        f"• {SERVICE_PORTFOLIO[k]}" for k in ctx["service_keys"] if k in SERVICE_PORTFOLIO
    )

    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_email_prompt(lead: dict) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) ready to be sent to the LLM.

    The current date is injected both into the system and user prompts so the
    model is forced to reason in the present, never defaulting to stale timelines.
    """
    ctx = get_smart_context(lead)
    now = datetime.now()
    today_str = now.strftime("%B %d, %Y")   # e.g. "February 22, 2026"
    year = now.year

    system_prompt = (
        f"You are a Senior Partner at CyberArc MSP — a B2B strategic outreach specialist. "
        f"TODAY IS {today_str} ({year}). "
        f"CRITICAL: never reference {year - 1} or {year - 2} as 'current' or 'this year'. "
        f"All industry insights, regulations, and market pressures must reflect {year} realities. "
        f"Output ONLY valid JSON. No prose before or after. Schema: "
        f'{{ "subject": "string under 60 chars", "bodyHtml": "HTML email body string, NO signature block" }}'
    )

    user_prompt = f"""
RECIPIENT
  Name:     {lead.get('first_name', 'there')} {lead.get('last_name', '')}
  Role:     {lead.get('role', 'Executive')}
  Company:  {lead.get('company', 'their organisation')}
  Industry: {lead.get('industry', 'Technology')}
  Location: {lead.get('location', 'Global')}
  Employees:{lead.get('employees', 'undisclosed')}

TODAY: {today_str}
INDUSTRY HOOK: {ctx['hook']}
COMPLIANCE ANGLE: {ctx['risk']}

AVAILABLE SERVICES WE CAN OFFER THEM:
{ctx['services_text']}

WRITING MISSION:
Write a consultative B2B cold email (160–200 words body). Rules:
1. Open with "Hi {lead.get('first_name', 'there')},"
2. HOOK: One sharp observation about their industry + location in {year} (no filler).
3. PAIN: Frame as "As [Role], you're balancing X with Y. What we see is [specific problem]."
4. Use exactly this phrase: "Three ways we help:"
5. LIST: <ul><li><strong>Pillar Header:</strong> One-sentence description with a metric.</li></ul> — exactly 3 items, 50% tech + 50% risk/compliance angle spread.
6. Proof: One line referencing similar clients or a benchmark result.
7. CTA: End with "Open for 15 minutes this week?" followed by a new line "Best,"
8. NO closing name — signature is appended by the system.
9. Subject: under 60 characters, professional, curiosity-driven.
10. Use <p> and <ul><li><strong> tags only. No inline styles.

Output JSON now:
""".strip()

    return system_prompt, user_prompt
