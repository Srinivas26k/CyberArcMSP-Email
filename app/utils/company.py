"""
company.py — Brand context, service portfolio, and email template builder for CyberArc MSP.

This file is the SINGLE source of truth for all company-specific content.
Update this file to change branding, services, or email design.
"""
import re
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# COMPANY PROFILE
# ─────────────────────────────────────────────────────────────────────────────

COMPANY_PROFILE = {
    "name":      "CyberArc MSP",
    "website":   "https://cyberarcmsp.com",
    "logo_url":  "https://cyberarcmsp.com/logo.png",
    "calendly":  "https://calendly.com/contact-cyberarcmsp/30min",
    "offices":   "Hyderabad • London • Dubai • Toronto • Wyoming • Melbourne",
    "tagline":   "Enterprise-Grade Security & Technology for the Modern Enterprise",
}

SENDER_DEFAULTS = {
    "name":  "CyberArc MSP",
    "title": "Enterprise Solutions Architect",
    "email": "contact.cyberarcmsp@gmail.com",
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
# EMAIL HTML TEMPLATE BUILDER  (mobile-responsive)
# ─────────────────────────────────────────────────────────────────────────────

_PLACEHOLDER_RE = re.compile(r'\{\{([A-Z_]+)\}\}')


def _build_cta_button(calendly_url: str) -> str:
    """Build the centred booking CTA button HTML. Returns empty string if no URL."""
    if not calendly_url:
        return ""
    now = datetime.now()
    url = f"{calendly_url}?month={now.year}-{now.month:02d}"
    return (
        '<div style="margin:28px auto;text-align:center;padding:0 24px;">'
        f'  <a href="{url}"'
        '     style="display:inline-block;padding:14px 32px;background:#0056b3;color:#ffffff;'
        '            text-decoration:none;font-weight:700;border-radius:6px;font-size:15px;'
        '            letter-spacing:0.3px;box-shadow:0 3px 8px rgba(0,86,179,0.3);'
        '            mso-padding-alt:14px 32px;">'
        '    &#128197; Book a 15-Minute Strategy Call'
        '  </a>'
        '</div>'
    )


def render_custom_template(html_tpl: str, **ctx) -> str:
    """
    Render a user-supplied HTML template by substituting {{PLACEHOLDER}} tokens.

    Available tokens (all optional except {{BODY}}):
        {{BODY}}             — AI-generated email body HTML  (REQUIRED)
        {{CTA_BUTTON}}       — Booking button HTML (auto-built from calendly_url)
        {{SENDER_NAME}}      — Sender full name
        {{SENDER_TITLE}}     — Sender title / role
        {{SENDER_EMAIL}}     — Sender email address
        {{COMPANY_NAME}}     — Company / brand name
        {{COMPANY_TAGLINE}}  — One-line company tagline
        {{COMPANY_LOGO}}     — Logo image URL
        {{COMPANY_WEBSITE}}  — Company website URL
        {{OFFICES}}          — Office locations string
        {{YEAR}}             — Current year (4-digit)
    """
    mapping = {
        'BODY':            ctx.get('inner_html', ''),
        'CTA_BUTTON':      _build_cta_button(ctx.get('calendly_url', '')),
        'SENDER_NAME':     ctx.get('sender_name', ''),
        'SENDER_TITLE':    ctx.get('sender_title', ''),
        'SENDER_EMAIL':    ctx.get('sender_email', ''),
        'COMPANY_NAME':    ctx.get('company_name', ''),
        'COMPANY_TAGLINE': ctx.get('company_tagline', ''),
        'COMPANY_LOGO':    ctx.get('company_logo', ''),
        'COMPANY_WEBSITE': ctx.get('company_website', ''),
        'OFFICES':         ctx.get('offices', ''),
        'YEAR':            str(datetime.now().year),
    }
    return _PLACEHOLDER_RE.sub(lambda m: mapping.get(m.group(1), m.group(0)), html_tpl)


def wrap_email_template(
    inner_html: str,
    sender_email: str,
    sender_name: str  = SENDER_DEFAULTS["name"],
    sender_title: str = SENDER_DEFAULTS["title"],
    calendly_url: str = COMPANY_PROFILE["calendly"],
    company_name: str = COMPANY_PROFILE["name"],
    company_tagline: str = COMPANY_PROFILE["tagline"],
    company_logo: str = COMPANY_PROFILE["logo_url"],
    company_website: str = COMPANY_PROFILE["website"],
    offices: str = COMPANY_PROFILE["offices"],
) -> str:
    """
    Wraps the AI-generated email body in a branded, mobile-responsive HTML shell.

    Key design decisions:
    • max-width 620 px — renders cleanly in Gmail, Outlook, Apple Mail.
    • Fluid images (max-width:100%) prevent overflow on small screens.
    • Footer switches from 2-column → stacked on mobile via media query.
    • Sender name + title appended directly below "Best," so every email
    Make sure after the "Best," tag, there is a <p>{SENDER_NAME}</p>
    """
    now = datetime.now()
    cta_html = _build_cta_button(calendly_url)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Email from {COMPANY_PROFILE['name']}</title>
  <style>
    /* ── Reset ── */
    body,table,td,a{{-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;}}
    table,td{{mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;}}
    img{{-ms-interpolation-mode:bicubic;border:0;display:block;max-width:100%;}}
    /* ── Body ── */
    body{{margin:0;padding:0;background:#f0f2f5;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;}}
    /* ── Wrapper ── */
    .email-wrapper{{width:100%;background:#f0f2f5;padding:32px 0;}}
    .email-card{{max-width:620px;margin:0 auto;background:#ffffff;border-radius:10px;
                 overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);border:1px solid #e1e4e8;}}
    /* ── Header ── */
    .email-header{{padding:22px 32px;border-bottom:3px solid #0056b3;background:#fff;}}
    .email-header img{{width:46px;height:auto;display:inline-block;vertical-align:middle;margin-right:12px;}}
    .email-header .brand-name{{font-size:20px;font-weight:700;color:#111;letter-spacing:-0.4px;
                               vertical-align:middle;display:inline-block;}}
    /* ── Body ── */
    .email-body{{padding:32px 36px 16px;color:#1a1a1a;font-size:16px;line-height:1.7;}}
    .email-body p{{margin:0 0 16px;}}
    .email-body ul{{margin:12px 0 20px;padding-left:22px;}}
    .email-body li{{margin-bottom:12px;}}
    .email-body strong{{color:#0056b3;}}
    /* ── Signature block ── */
    .email-sig{{padding:16px 36px 0;font-size:15px;color:#333;line-height:1.6;}}
    .email-sig .sig-name{{font-weight:700;color:#0056b3;font-size:16px;}}
    .email-sig .sig-title{{color:#666;font-size:14px;}}
    /* ── CTA ── */
    .email-cta{{padding:8px 0;}}
    /* ── Footer ── */
    .email-footer{{background:#f8f9fa;padding:24px 32px;border-top:1px solid #eee;font-size:13px;color:#666;}}
    .footer-row{{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;}}
    .footer-left{{flex:1;min-width:160px;}}
    .footer-right{{text-align:right;min-width:120px;}}
    .footer-right p{{font-size:11px;color:#aaa;line-height:1.9;margin:0;}}
    .footer-legal{{margin-top:16px;font-size:11px;color:#bbb;text-align:center;}}
    a.footer-link{{color:#0056b3;text-decoration:none;font-weight:500;}}
    a.footer-sub{{color:#999;text-decoration:none;}}
    /* ── Mobile ── */
    @media only screen and (max-width:480px){{
      .email-card{{border-radius:0!important;box-shadow:none!important;border-left:none!important;border-right:none!important;}}
      .email-wrapper{{padding:0!important;}}
      .email-header{{padding:18px 20px!important;}}
      .email-body{{padding:24px 20px 12px!important;font-size:15px!important;}}
      .email-sig{{padding:12px 20px 0!important;}}
      .email-footer{{padding:20px!important;}}
      .footer-row{{flex-direction:column!important;}}
      .footer-right{{text-align:left!important;}}
      .email-body strong{{display:block;margin-bottom:2px;}}
    }}
  </style>
</head>
<body>
<div class="email-wrapper">
  <div class="email-card">

    <!-- HEADER -->
    <div class="email-header">
      <img src="{company_logo}" alt="{company_name}" width="46">
      <span class="brand-name">{company_name}</span>
    </div>

    <!-- BODY (AI-generated) + dynamic sign-off -->
    <div class="email-body">
      {inner_html}
      <p style="margin:20px 0 2px 0;"><strong>{sender_name}</strong><br>
      <span style="font-size:13px;color:#666;">{sender_title} | {company_name}</span></p>
    </div>

    <!-- CTA -->
    <div class="email-cta">
      {cta_html}
    </div>

    <!-- FOOTER -->
    <div class="email-footer">
      <div class="footer-row">
        <div class="footer-left">
          <p style="margin:0 0 4px;font-weight:600;color:#333;">{company_name}</p>
          <p style="margin:0 0 4px;font-size:12px;color:#999;">{company_tagline}</p>
          {f'<p style="margin:0;font-size:12px;"><a href="{company_website}" class="footer-link" style="color:#0056b3;text-decoration:none;font-weight:500;">{company_website}</a></p>' if company_website else ''}
        </div>
        <div class="footer-right">
          <p>Global Operations<br>{offices}</p>
        </div>
      </div>
      <div class="footer-legal">
        &copy; {now.year} {company_name}. All rights reserved. Privileged &amp; Confidential.<br>
        To unsubscribe, reply <em>Unsubscribe</em>.
      </div>
    </div>

  </div>
</div>
</body>
</html>""".strip()
