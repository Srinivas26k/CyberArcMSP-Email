"""
company.py — Brand context, service portfolio, and email template builder for CyberArc MSP.

This file is the SINGLE source of truth for all company-specific content.
Update this file to change branding, services, or email design.
"""
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# COMPANY PROFILE
# ─────────────────────────────────────────────────────────────────────────────

COMPANY_PROFILE = {
    "name":        "CyberArc MSP",
    "website":     "https://cyberarcmsp.com",
    "logo_url":    "https://cyberarcmsp.com/logo.png",
    "calendly":    "https://calendly.com/cyberarcmsp/30min",
    "offices":     "Hyderabad • London • Dubai • Toronto • Wyoming • Melbourne",
    "tagline":     "Enterprise-Grade Security & Technology for the Modern Enterprise",
}

SENDER_DEFAULTS = {
    "name":   "CyberArc MSP",
    "title":  "Enterprise Solutions Architect",
    "email":  "contact.cyberarcmsp@gmail.com",
}


# ─────────────────────────────────────────────────────────────────────────────
# SERVICE PORTFOLIO
# Nine practice areas — used by prompt.py to tailor emails to the lead's context
# ─────────────────────────────────────────────────────────────────────────────

SERVICE_PORTFOLIO = {
    "cybersecurity": (
        "SOC/NOC 24/7 AI-driven threat detection, VAPT & Red Team exercises, "
        "Zero Trust architecture, Cloud Security hardening (AWS/Azure/GCP). "
        "Average: 68% reduction in mean-time-to-detect."
    ),
    "ai_toolkit": (
        "AI Automation reducing operational overhead by 40%, "
        "GovOps policy-enforcement bots, AIOps event correlation & alert de-duplication."
    ),
    "saas_services": (
        "Custom multi-tenant SaaS platforms, GDPR/CCPA embedded architecture, "
        "Legacy modernisation with zero downtime migrations."
    ),
    "audit_compliance": (
        "GRC advisory: SOC 2 Type II, PCI DSS 4.0, HIPAA, GDPR, ISO 27001. "
        "IAM & Privileged Access Management. Audit-ready in 90 days."
    ),
    "aiml_services": (
        "Custom enterprise LLMs with safety rails & hallucination guards, "
        "Data strategy with governance frameworks, Predictive analytics at scale."
    ),
    "cloud_devsecops": (
        "Multi-cloud governance & cost optimisation, DevSecOps CI/CD security gates, "
        "Terraform/Ansible IaC with policy-as-code."
    ),
    "c_level_advisory": (
        "vCISO/vCIO strategic leadership, Board-level reporting & risk quantification, "
        "FinOps for CFOs — typically 30-40% cloud spend reduction."
    ),
    "strategic_staffing": (
        "Top 1% technical talent: Cybersecurity, AI/ML, Cloud. "
        "Background-vetted, NDA-signed, ready in under 2 weeks."
    ),
    "corporate_training": (
        "Cybersecurity awareness programmes, Phishing defence drills, "
        "Certification validation (CISSP, CISM, AWS, Azure)."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL HTML TEMPLATE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def wrap_email_template(
    inner_html: str,
    sender_email: str,
    sender_name: str = SENDER_DEFAULTS["name"],
    sender_title: str = SENDER_DEFAULTS["title"],
    calendly_url: str = COMPANY_PROFILE["calendly"],
) -> str:
    """
    Wraps the AI-generated email body in the branded CyberArc MSP HTML shell.
    Injects the current month into the Calendly URL for accurate scheduling availability.
    """
    now = datetime.now()
    calendly_month = f"{calendly_url}?month={now.year}-{now.month:02d}"

    cta_button = f"""
    <div style="margin: 30px 40px; text-align: center;">
      <a href="{calendly_month}"
         style="display:inline-block;padding:13px 28px;background:#0056b3;color:#fff;
                text-decoration:none;font-weight:600;border-radius:5px;font-size:15px;
                letter-spacing:0.4px;box-shadow:0 2px 6px rgba(0,86,179,0.25);">
        📅 Book a Strategy Call
      </a>
    </div>
    """ if calendly_url else ""

    return f"""
<div style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;background-color:#f4f6f8;padding:40px 0;">
  <div style="max-width:620px;margin:0 auto;background:#fff;border-radius:8px;
              overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,0.06);border:1px solid #e1e4e8;">

    <!-- HEADER -->
    <div style="padding:24px 40px;border-bottom:2px solid #0056b3;background:#fff;">
      <table style="width:100%;border-collapse:collapse;"><tr>
        <td style="width:52px;vertical-align:middle;">
          <img src="{COMPANY_PROFILE['logo_url']}" alt="{COMPANY_PROFILE['name']}"
               style="width:48px;height:auto;display:block;">
        </td>
        <td style="vertical-align:middle;padding-left:14px;">
          <span style="font-size:20px;font-weight:700;color:#111;letter-spacing:-0.5px;">
            {COMPANY_PROFILE['name']}
          </span>
        </td>
      </tr></table>
    </div>

    <!-- BODY -->
    <div style="padding:36px 40px 20px;color:#222;font-size:16px;line-height:1.65;">
      {inner_html}
    </div>

    <!-- CTA -->
    {cta_button}

    <!-- FOOTER -->
    <div style="background:#f8f9fa;padding:28px 40px;border-top:1px solid #eee;font-size:14px;color:#555;">
      <table style="width:100%;border-collapse:collapse;"><tr>
        <td style="vertical-align:top;">
          <p style="margin:0 0 4px;"><strong style="color:#0056b3;font-size:15px;">{sender_name}</strong></p>
          <p style="margin:0 0 14px;color:#666;">{sender_title}</p>
          <p style="margin:0;line-height:1.9;">
            <a href="{COMPANY_PROFILE['website']}" style="color:#0056b3;text-decoration:none;font-weight:500;">
              {COMPANY_PROFILE['website'].replace('https://','')}
            </a><br>
            <a href="mailto:{sender_email}" style="color:#777;text-decoration:none;">{sender_email}</a>
          </p>
        </td>
        <td style="text-align:right;vertical-align:top;">
          <p style="margin:0;font-size:12px;color:#aaa;line-height:1.8;">
            Global Operations<br>{COMPANY_PROFILE['offices']}
          </p>
        </td>
      </tr></table>
      <div style="margin-top:18px;font-size:11px;color:#bbb;text-align:center;">
        © {now.year} {COMPANY_PROFILE['name']}. All rights reserved. · Privileged &amp; Confidential.<br>
        To unsubscribe, simply reply <em>Unsubscribe</em>.
      </div>
    </div>

  </div>
</div>
""".strip()
