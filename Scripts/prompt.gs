/**
 * prompt.gs
 * Enhanced AI Prompt Engineering & Service Context
 * Version: v34
 * Focus: 50% Technology / 50% Risk Governance & Compliance
 */

// ============================================================
// 📚  SERVICE CATALOG (ENHANCED)
// ============================================================

const SERVICE_PORTFOLIO = {
  cybersecurity: `
    **Cybersecurity Services (Tech & Compliance):**
    - **SOC/NOC:** 24/7 AI-driven monitoring (Tech) aligned with incident reporting standards (Compliance).
    - **VAPT:** Automated vulnerability assessments (Tech) satisfying regulatory audit requirements (Compliance).
    - **Zero Trust:** Identity-first security architecture (Tech) ensuring data access governance (Compliance).
    - **Cloud Security:** Hardening across AWS/Azure/GCP (Tech) to meet CIS Benchmarks (Compliance).
    - **Outcome:** Technical resilience meets audit readiness.`,
  
  ai_toolkit: `
    **AI-Powered Toolkit (Tech & Optimization):**
    - **Automation:** Proprietary scripts reducing manual overhead by 40% (Tech).
    - **GovOps:** AI-driven policy enforcement and audit trails (Compliance).
    - **AIOps:** Event correlation (BigPanda) and incident intelligence (Tech).
    - **Outcome:** Faster resolution with full regulatory traceability.`,
  
  saas_services: `
    **SaaS Services (Development & Governance):**
    - **Engineering:** Custom multi-tenant platforms with secure SDLC (Tech).
    - **Compliance by Design:** GDPR/CCPA controls embedded in architecture (Compliance).
    - **Modernization:** Legacy refactoring ensuring data sovereignty (Tech/Compliance).
    - **Outcome:** Scalable, secure, and compliant software delivery.`,
  
  audit_compliance: `
    **Audit & Compliance (Governance Core):**
    - **GRC Strategy:** Advisory for SOC 2, PCI DSS, HIPAA, GDPR, ISO 27001, FedRAMP.
    - **Audit Readiness:** Gap analysis, security audits, continuous monitoring.
    - **IAM:** Enterprise identity governance, SSO, MFA, privileged access management.
    - **Outcome:** Full regulatory compliance, reduced legal risk, streamlined audits.`,
  
  aiml_services: `
    **AI/ML Services (Innovation & Risk):**
    - **GenAI & LLMs:** Custom enterprise LLMs with bias detection/safety rails (Tech/Risk).
    - **Data Strategy:** Modernizing data warehouses with strict data governance/lineage (Tech/Compliance).
    - **Predictive Analytics:** Forecasting trends while maintaining data privacy (Tech).
    - **Outcome:** Responsible AI adoption with governed data infrastructure.`,
  
  cloud_devsecops: `
    **Cloud & DevSecOps (Speed & Control):**
    - **Cloud Strategy:** Multi-cloud governance (AWS/Azure/GCP) for cost and policy control (Compliance).
    - **DevSecOps:** Security gates in CI/CD pipelines (Tech) for continuous compliance.
    - **Infrastructure as Code (IaC):** Audit-ready provisioning via Terraform/Ansible (Tech/Compliance).
    - **Outcome:** Rapid migration with embedded security controls.`,
  
  c_level_advisory: `
    **Virtual C-Level Advisory (Strategy & Risk):**
    - **vCISO/vCIO:** Strategic leadership balancing tech innovation with enterprise risk (Risk).
    - **Executive Focus:** Operational resilience, ROI validation, and board-level reporting.
    - **For CFOs:** Predictable IT spending and cloud cost governance (FinOps).
    - **Outcome:** Quantifiable risk reduction and aligned business/tech strategy.`,
  
  strategic_staffing: `
    **Strategic Staffing (Talent & Vetting):**
    - **Headhunting:** Top 1% technical talent (Cybersecurity, AI, Cloud).
    - **Vetting:** Background checks and skill validation ensuring team integrity.
    - **Outcome:** Access to elite talent with reduced hiring risk.`,
  
  corporate_training: `
    **Corporate Training (Human Firewall):**
    - **Upskilling:** Cybersecurity awareness, Phishing defense (Risk Reduction).
    - **Certifications:** Training validation for internal audit requirements (Compliance).
    - **Outcome:** Reduced human error and documented staff competency.`,
  
  financial_reports: `
    **Financial Reports (Transparency):**
    - **Visibility:** Real-time IT spend vs ROI dashboards.
    - **Governance:** Audit-ready infrastructure financial records (Compliance).
    - **Outcome:** Crystal-clear visibility and seamless financial audits.`
};

// ============================================================
// 🕵️  SMART CONTEXT ENGINE (MOVED & ENHANCED)
// ============================================================

function getSmartContext(lead) {
  var text = (lead.company + " " + lead.industry).toLowerCase();
  var loc = (lead.location || "").toLowerCase();
  var role = (lead.role || "").toLowerCase();
  
  var key = "generic";
  var context_hook = "Global operational pressure";
  var risk_focus = "General Compliance";

  // Enriched Context Logic
  if (text.match(/msp|it service|consulting/) && text.match(/manufact|factory|production/)) {
    key = "msp_manufacturing";
    context_hook = "Securing supply chains and OT environments for manufacturing clients";
    risk_focus = "Third-party Risk Management (TPRM) & Supply Chain Security";
  } else if (text.match(/oil|gas|petro|refin|energy/)) {
    key = "energy";
    context_hook = "Critical infrastructure protection and OT/IT convergence";
    risk_focus = "NERC CIP compliance & HSE data integrity";
  } else if (text.match(/manufact|factory|steel|production|heavy|industr/)) {
    key = "manufacturing";
    context_hook = "Smart factory automation and SCADA security risks";
    risk_focus = "IEC 62443 standards & Intellectual Property protection";
  } else if (text.match(/bank|financ|invest|capital|fund/)) {
    key = "bfsi";
    context_hook = "High-frequency trading resilience and cross-border data flows";
    risk_focus = "SEC/GLBA regulations, PCI DSS, & SWIFT security compliance";
  } else if (text.match(/health|medic|pharma/)) {
    key = "healthcare";
    context_hook = "Patient data integrity and medical IoT (IoMT) vulnerabilities";
    risk_focus = "HIPAA compliance & PHI data governance";
  } else if (text.match(/infra|construct|build|engineer/)) {
    key = "infrastructure";
    context_hook = "Scalable project delivery and secure remote site connectivity";
    risk_focus = "ISO 27001 certification & Project data confidentiality";
  }

  var relevantServices = [];
  
  // Service Mapping based on Role
  if (role.match(/cfo|finance|md|managing director|ceo|president/)) {
    relevantServices.push(SERVICE_PORTFOLIO.c_level_advisory, SERVICE_PORTFOLIO.financial_reports, SERVICE_PORTFOLIO.strategic_staffing);
  } else if (role.match(/ciso|security|risk/)) {
    relevantServices.push(SERVICE_PORTFOLIO.cybersecurity, SERVICE_PORTFOLIO.audit_compliance, SERVICE_PORTFOLIO.ai_toolkit);
  } else if (role.match(/cto|cio|tech|engineer|architect/)) {
    relevantServices.push(SERVICE_PORTFOLIO.cloud_devsecops, SERVICE_PORTFOLIO.saas_services, SERVICE_PORTFOLIO.aiml_services);
  } else {
    // Fallback based on Industry Key
    if (key === "infrastructure") {
       relevantServices.push(SERVICE_PORTFOLIO.cloud_devsecops, SERVICE_PORTFOLIO.c_level_advisory);
    } else if (key === "energy" || key === "manufacturing") {
      relevantServices.push(SERVICE_PORTFOLIO.c_level_advisory, SERVICE_PORTFOLIO.ai_toolkit);
    } else {
      relevantServices.push(SERVICE_PORTFOLIO.c_level_advisory, SERVICE_PORTFOLIO.cybersecurity);
    }
  }

  return {
    key: key,
    hook: context_hook,
    risk: risk_focus,
    services: relevantServices.join("\n"),
    location: lead.location || "Global"
  };
}


// ============================================================
// 🧠  CONSTRUCT OPTIMIZED PROMPT (v34)
// ============================================================

function constructPrompt(lead, todayDate) {
  var ctx = getSmartContext(lead);
  
  // Build company scale context (for AI only, never printed)
  var scaleHint = "";
  if (lead.employees) {
    var emp = String(lead.employees).replace(/[~,]/g, "");
    var num = parseInt(emp);
    if (!isNaN(num)) {
      if (num < 50) scaleHint = "startup scale";
      else if (num < 200) scaleHint = "mid-market";
      else scaleHint = "enterprise scale";
    }
  }

  return `
You are a Senior Partner at CyberArc MSP writing to ${lead.first} (${lead.role}) at ${lead.company}.

**TEMPORAL CONTEXT:**
- **CURRENT DATE:** ${todayDate || "Today"}
- **Mission:** Ensure the email feels timely and relevant to *right now*.

**RECIPIENT CONTEXT:**
- Company: ${lead.company}
- Role: ${lead.role}
- Industry: ${lead.industry || "Technology"}
- Location: ${ctx.location}
- Scale: ${scaleHint || "established company"}

**STRATEGIC ALIGNMENT (THE "WHY"):**
- **Industry Focus:** ${ctx.key}
- **Tech Challenge:** ${ctx.hook}
- **Compliance/Risk Focus:** ${ctx.risk}

**AVAILABLE SERVICES (Select relevant points):**
${ctx.services}

**YOUR MISSION:**
Write a consultative, high-value B2B email that is "perfectly length" (approx 150-200 words) - deep enough to show expertise, short enough to be read.

**CRITICAL REQUIREMENT - THE 50:50 RATIO:**
You MUST balance the conversation 50% on Advanced Technology (AI, Cloud, Automation) and 50% on Risk Governance & Compliance (Audit, Regulation, Data Safety).
- Do not just talk about tech tools; explain how they ensure compliance.
- Do not just talk about regulations; explain how tech automates adherence.

**CORRELATION MAPPING:**
Explicitly map the correlation between CyberArc MSP's capabilities and ${lead.company}'s likely goals.
- *Example:* "For a firm like ${lead.company}, the correlation between [Tech: e.g., cloud agility] and [Risk: e.g., data sovereignty] is the critical success factor we address."

**STRUCTURE:**
1. **Subject:** "${lead.company} — [Strategic Goal]" (under 60 chars, professional, impactful)
2. **Opening:** "Hi ${lead.first}," + A highly specific observation linking ${ctx.location}, their industry, and the current Tech/Compliance landscape.
3. **The Correlation (The Core):** "As ${lead.role}, you likely see that [Industry Challenge] requires a balance of innovation and control. The correlation is clear: you cannot scale [Tech] without robust [Compliance]."
4. **The Solution (50:50 Blend):** List 3 bullet points. Each point MUST combine a Tech Solution with a Risk/Compliance outcome.
    - *Format:* "**[Service]:** [Technical Action] ensuring [Compliance/Risk Result]."
5. **Proof:** "We've helped similar firms in ${ctx.location} harmonize their tech stack with regulatory demands."
6. **CTA:** "Let's discuss how we can map this correlation to your specific goals. Open for 15 mins?"

**TONE:**
- Professional, authoritative, yet approachable.
- "Best Services" mentality: confident in the premium nature of the offering.
- Content-rich: Every sentence must add value. No fluff.

**OUTPUT:** Return ONLY valid JSON:
{"subject":"...","bodyHtml":"...(HTML body with <p>, <ul>, <li>, <strong> tags ONLY. No signature.)"}
`;
}
