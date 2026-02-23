"""
prompt.py — LLM prompt construction for SRV AI Email Outreach.

Key design principles:
  • Temporal anchoring: always injects today's exact date so the AI never drifts.
  • Deep specificity: location-aware regulatory hooks, role-specific pain framing, named metrics.
  • 3 named CyberArc MSP service pillars, each with a real benchmark stat.
  • Output contract: JSON only, {"subject": "...", "bodyHtml": "..."}
"""
import re
from datetime import datetime
from company import SERVICE_PORTFOLIO


# ─────────────────────────────────────────────────────────────────────────────
# INDUSTRY → CONTEXT MAPPING
# Each tuple: (regex, key, hook, risk_focus, relevant_service_keys, metric_example)
# ─────────────────────────────────────────────────────────────────────────────

_INDUSTRY_CONTEXTS = [
    (
        r"oil|gas|petro|energy|power|utilities",
        "energy",
        "Critical OT/IT convergence as NERC CIP v7 enforcement tightens across {location}",
        "NERC CIP v7, HSE & IEC 62443 compliance for operational continuity",
        ["c_level_advisory", "cybersecurity"],
        "A Texas energy operator cut breach-to-containment from 72 h to 9 min and passed a surprise NERC audit without findings.",
    ),
    (
        r"bank|financ|invest|capital|bfsi|fund|payment",
        "bfsi",
        "High-frequency trading resilience & cross-border data integrity as PCI DSS 4.0 mandate hits {location} fintechs",
        "SEC, GLBA, PCI DSS 4.0 & SWIFT security frameworks",
        ["cybersecurity", "audit_compliance"],
        "A Portland payments processor released new credit products 24% faster and passed SOC-2 without manual evidence collection.",
    ),
    (
        r"health|medic|pharma|biotech|hospital|clinic|hmo",
        "healthcare",
        "Patient-data integrity & medical-IoT (IoMT) vulnerabilities as HIPAA enforcement intensifies in {location}",
        "HIPAA §164.312, HITECH & PHI data governance",
        ["cybersecurity", "audit_compliance"],
        "A Dallas oncology network saw a 42% drop in anomalous device commands and cut quarterly HIPAA audit prep from 180 staff-hours to 28.",
    ),
    (
        r"manufact|factory|steel|industr|automat|oem|machiner",
        "manufacturing",
        "Smart-factory SCADA hardening & IP-theft prevention as IEC 62443 audits expand in {location}",
        "IEC 62443, NIST CSF & supply-chain third-party risk controls",
        ["ai_toolkit", "cloud_devsecops"],
        "A Midwest industrial OEM eliminated 3 critical SCADA vulnerabilities and achieved IEC 62443 SL-2 in under 90 days.",
    ),
    (
        r"saas|software|tech|startup|platform|app",
        "saas",
        "Rapid product scaling vs. accumulating security debt as SOC 2 Type II becomes table-stakes for {location} buyers",
        "SOC 2 Type II, data sovereignty & GDPR/CCPA",
        ["saas_services", "aiml_services"],
        "A SaaS platform in Singapore achieved SOC 2 Type II in 11 weeks and reduced security review blockers on enterprise deals by 60%.",
    ),
    (
        r"retail|ecom|consumer|fmcg|commerce",
        "retail",
        "Omnichannel fraud vectors & POS/API exposure as PCI DSS 4.0 deadline hits {location} retailers",
        "PCI DSS 4.0 & consumer data regulations",
        ["cybersecurity", "audit_compliance"],
        "A Dubai e-commerce group cut card-not-present fraud by 38% and achieved PCI DSS 4.0 compliance 6 weeks ahead of deadline.",
    ),
    (
        r"telecom|telco|isp|network|carrier",
        "telecom",
        "Network infrastructure integrity & NIS2 Directive pressure affecting {location} carriers",
        "FCC, NIS2 Directive & carrier-grade security hardening",
        ["cybersecurity", "cloud_devsecops"],
        "A European telco reduced NOC alert noise by 61% using AI event correlation and passed NIS2 readiness assessment without findings.",
    ),
    (
        r"edu|university|school|academy|college",
        "education",
        "Research IP protection & ransomware targeting academic networks in {location}",
        "FERPA & NIST Cybersecurity Framework for research institutions",
        ["cybersecurity", "corporate_training"],
        "A UK research university recovered from a ransomware simulation in under 4 hours and reduced phishing click-rates by 73% after a 6-week awareness programme.",
    ),
    (
        r"gov|government|public|minister|municipal|federal",
        "government",
        "Nation-state threats to critical national infrastructure in {location} under FedRAMP and Cyber Essentials mandates",
        "FISMA, Cyber Essentials & FedRAMP ATO",
        ["cybersecurity", "audit_compliance"],
        "A municipal agency achieved FedRAMP Ready status in 14 weeks and reduced mean-time-to-detect on its SOC from 8 hours to 22 minutes.",
    ),
]

_ROLE_OVERRIDES = [
    (r"cfo|chief financial|treasurer",                ["c_level_advisory", "audit_compliance"]),
    (r"ceo|chief executive|md |president|founder",    ["c_level_advisory", "cybersecurity"]),
    (r"ciso|chief information security|vp security",  ["cybersecurity", "audit_compliance", "ai_toolkit"]),
    (r"cto|chief technology|vp engineering",          ["cloud_devsecops", "aiml_services"]),
    (r"cio|chief information|head it|director it",    ["cloud_devsecops", "audit_compliance"]),
    (r"risk|compliance|audit|legal|grc|ccо|cco",      ["audit_compliance", "c_level_advisory"]),
    (r"hr|people|talent|culture",                     ["strategic_staffing", "corporate_training"]),
    (r"head of|vp of|director of|svp",                ["c_level_advisory", "cybersecurity"]),
]

# Map service key → short punchy name displayed as <strong> header in emails
_SERVICE_NAMES = {
    "cybersecurity":    "Zero-Trust SOC/NOC Fusion",
    "ai_toolkit":       "AI-Driven Automation",
    "saas_services":    "Secure SaaS Engineering",
    "audit_compliance": "GRC & Compliance Automation",
    "aiml_services":    "GenAI & Data Intelligence",
    "cloud_devsecops":  "DevSecOps & FinOps",
    "c_level_advisory": "vCISO / Executive Advisory",
    "strategic_staffing": "Elite Technical Staffing",
    "corporate_training": "Human-Firewall Training",
}


def get_smart_context(lead: dict) -> dict:
    """
    Analyses the lead's company, industry, role, and location to select the most
    relevant CyberArc service pillars and compliance angle.
    """
    text     = f"{lead.get('company', '')} {lead.get('industry', '')}".lower()
    role     = lead.get("role", "").lower()
    location = lead.get("location", "Global")

    ctx = {
        "key":          "technology",
        "hook":         f"Digital transformation pressure and an evolving cyber-threat landscape in {location}",
        "risk":         "General compliance & data governance obligations",
        "service_keys": ["c_level_advisory", "cybersecurity"],
        "proof":        "We've helped similar organisations compress breach-to-containment time from 72 hrs to under 10 minutes.",
    }

    # Industry match (first wins)
    for pattern, key, hook_tpl, risk, services, proof in _INDUSTRY_CONTEXTS:
        if re.search(pattern, text):
            ctx.update(
                key=key,
                hook=hook_tpl.format(location=location),
                risk=risk,
                service_keys=services,
                proof=proof,
            )
            break

    # Role-level override (more specific)
    for pattern, services in _ROLE_OVERRIDES:
        if re.search(pattern, role):
            ctx["service_keys"] = services
            break

    # Build named pillars list for the prompt
    ctx["named_pillars"] = "\n".join(
        f"  Pillar {i+1} — \"{_SERVICE_NAMES.get(k, k)}\": {SERVICE_PORTFOLIO.get(k, '')}"
        for i, k in enumerate(ctx["service_keys"][:3])
    )

    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_email_prompt(lead: dict) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) ready to be sent to the LLM.
    """
    ctx      = get_smart_context(lead)
    now      = datetime.now()
    today    = now.strftime("%B %d, %Y")
    year     = now.year
    first    = lead.get("first_name", "there")
    role     = lead.get("role", "Executive")
    company  = lead.get("company", "your organisation")
    industry = lead.get("industry", "Technology")
    location = lead.get("location", "Global")
    employees = lead.get("employees", "")

    system_prompt = (
        f"You are a Senior Partner at CyberArc MSP writing a B2B outreach email. "
        f"TODAY IS {today} ({year}). "
        f"CRITICAL: never reference {year-1} or earlier as 'current'. "
        f"All regulatory references, market pressures, and statistics must reflect {year} realities. "
        f"Write like a seasoned consultant — specific, confident, no generic buzzwords. "
        f"Output ONLY valid JSON, no prose outside it. "
        f'Schema: {{ "subject": "string ≤60 chars", "bodyHtml": "HTML body string — NO signature, NO sender name" }}'
    )

    # Two high-quality few-shot examples that define the exact style
    few_shot = """
STYLE EXAMPLES (match this depth and specificity):

Example A (Healthcare / CCO):
  Subject: HCI's IoMT Gap — 3 Ways We Close It
  Body excerpt:
  <p>Houston's medical corridor is expanding fast, and Texas Health Services Authority's new
  data-integrity rules now require covered entities to prove continuous monitoring of every device
  that touches PHI. That puts HCI in the cross-hairs when infusion pumps, imaging gateways, and
  telehealth endpoints all sit on the same flat network.</p>
  <p>As Head of Risk-Management & CCO, you're balancing zero-tolerance for PHI alteration with
  the board's push to integrate AI-driven diagnostics. What we see is IoMT traffic that bypasses
  NAC, undocumented service accounts, and patch windows too short for FDA-validated firmware.</p>
  <p>How CyberArc MSP closes the gap:</p>
  <ul>
    <li><strong>Zero-Trust SOC/NOC Fusion:</strong> We micro-segment each VLAN by device risk
    class, then feed CrowdStrike and Darktrace telemetry into our 24×7 AI SOC. Result: 42% drop
    in anomalous device commands for a Dallas oncology network within 90 days.</li>
    <li><strong>GRC & Compliance Automation:</strong> Continuous control mapping between
    HIPAA §164.312, NIST 800-53, and existing SOC 2 Type II evidence — last client cut quarterly
    HIPAA audit prep from 180 staff-hours to 28.</li>
    <li><strong>IoMT VAPT with Safe-Exploit Rollback:</strong> Pen-test against the MITRE IoMT
    matrix with compensating controls so FDA-valid devices stay untouched. A Houston ASC avoided
    $1.2 M in potential OCR fines after we found hard-coded credentials in PACS consoles.</li>
  </ul>
  <p>We've helped similar Texas HMOs compress breach-to-containment from 72 hrs to 9 mins
  and pass surprise OCR audits without findings.</p>
  <p>Open for 15 minutes this week?</p>
  <p>Best,</p>

Example B (Fintech / CIO):
  Subject: PortX Cloud Spend — 3 Levers Built for Bellevue
  Body excerpt:
  <p>Between the new WA FinTech credit-rating pilot and Seattle's cloud-premium power rates,
  Bellevue teams are under pressure to keep cloud spend lean while still shipping faster
  than the Bay.</p>
  <p>As CIO you're balancing zero-downtime mandates with run-rate cuts. What we see is
  burst-workload apps scaling 5× at month-end but never right-sizing after, so budgets spike
  just when compliance wants proof of control.</p>
  <p>How CyberArc MSP closes the gap:</p>
  <ul>
    <li><strong>DevSecOps & FinOps:</strong> We wire AWS Cost-Anomaly, Azure Budgets and
    Datadog into a single Terraform stack; every Friday it auto-spins dev clusters down and
    rightsizes RDS — clients see 18-28% OpEx drop within two sprints.</li>
    <li><strong>GRC & Compliance Automation:</strong> Shift-left pipeline with OPA policy
    checks so each container has already passed PCI-DSS and WA-state encryption rules before
    merge — pull-requests close 40% faster with zero audit findings.</li>
    <li><strong>GenAI & Data Intelligence:</strong> Fine-tuned LLM on transaction streams
    + RAG against Fed interchange updates; flags mule accounts 3× sooner, freeing L2 analysts
    for higher-value work.</li>
  </ul>
  <p>A Portland payments processor released new credit products 24% faster and passed their
  SOC-2 without manual evidence collection after the same engagement.</p>
  <p>Open for 15 minutes this week?</p>
  <p>Best,</p>
"""

    user_prompt = f"""
RECIPIENT
  First Name: {first}
  Full Role:  {role}
  Company:    {company}
  Industry:   {industry}
  Location:   {location}
  Employees:  {employees or 'undisclosed'}

TODAY: {today}
INDUSTRY HOOK (use this angle for the opening paragraph):
  {ctx['hook']}

COMPLIANCE / RISK FOCUS:
  {ctx['risk']}

CYBERARC MSP SERVICE PILLARS FOR THIS LEAD (use these as <strong> headers — exactly these names):
{ctx['named_pillars']}

PROOF POINT (adapt or use verbatim):
  {ctx['proof']}

{few_shot}

NOW WRITE THE EMAIL FOR {first.upper()} AT {company.upper()}:
Rules (follow every one — no exceptions):
1. Open: <p>Hi {first},</p>
2. HOOK paragraph (2-3 sentences): Name a specific, current regulatory change, market pressure,
   or technology shift happening in {location} that directly affects {company}'s {industry} sector
   in {year}. Be precise — name the regulation, the city, the deadline, the risk. No filler.
3. PAIN paragraph (2 sentences): "As {role}, you're balancing [tech initiative] with
   [compliance/cost pressure]. What we see is [3 specific technical problems] — name real
   attack vectors, misconfigurations, or compliance gaps relevant to their stack."
4. Section heading: <p><strong>How CyberArc MSP closes the gap:</strong></p>
5. Bullet list — exactly 3 <li> items. Each MUST:
   a. Start with the EXACT pillar name from above bolded in <strong>Pillar Name:</strong>
   b. Include ONE specific action we take (name a real tool, framework, or method)
   c. Include ONE measurable result with an actual number/percentage
   d. Be 2-3 sentences long. Not one generic sentence.
6. PROOF: One sentence referencing a real client type + location + quantified result.
7. CTA: <p>Open for 15 minutes this week?</p>
8. Close: <p>Best,</p>   ← DO NOT add any name or signature. System appends it.
9. Subject line: Specific to {company} — mention city/sector/regulation. Under 60 chars.
10. Use ONLY <p>, <ul>, <li>, <strong> tags. No inline styles. No <br> tags.
11. Target 220–270 words in the body.

Output JSON now:
""".strip()

    return system_prompt, user_prompt
