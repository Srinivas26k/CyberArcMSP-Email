"""
scoring.py — ICP (Ideal Customer Profile) lead scoring.

Scores a lead 0-100 based on publicly visible signals:
  - Seniority / decision-making power  (0-40 pts)
  - Company size                        (0-30 pts)
  - Profile completeness / data richness(0-30 pts)

The score is stored in Lead.lead_score and updated whenever a lead
is imported (CSV or Apollo) or manually re-scored via the API.
"""

_C_LEVEL  = {"ceo", "cto", "cfo", "coo", "ciso", "cso", "president",
              "founder", "owner", "partner", "managing director"}
_VP_LEVEL = {"vp", "vice president", "svp", "evp", "head of", "principal"}
_DIR_LEVEL = {"director", "chief of staff"}
_MGR_LEVEL = {"manager", "lead", "senior", "sr.", "sr "}


def score_lead(lead: dict) -> int:
    """Return an ICP score 0-100 for the given lead dict."""
    score = 0
    role      = (lead.get("role")      or "").lower()
    seniority = (lead.get("seniority") or "").lower()
    combined  = f"{role} {seniority}"

    # ── Seniority (0-40 pts) ─────────────────────────────────────────────────
    if any(kw in combined for kw in _C_LEVEL):
        score += 40
    elif any(kw in combined for kw in _VP_LEVEL):
        score += 30
    elif any(kw in combined for kw in _DIR_LEVEL):
        score += 22
    elif any(kw in combined for kw in _MGR_LEVEL):
        score += 12
    else:
        score += 5

    # ── Company size (0-30 pts) ───────────────────────────────────────────────
    raw_emp = (lead.get("employees") or "").replace(",", "").split("-")[0].strip()
    try:
        n = int(raw_emp)
        if n >= 5_000:
            score += 30
        elif n >= 1_000:
            score += 24
        elif n >= 200:
            score += 18
        elif n >= 50:
            score += 12
        elif n >= 10:
            score += 6
        else:
            score += 2
    except (ValueError, TypeError):
        score += 10  # unknown size — neutral

    # ── Profile completeness (0-30 pts) ──────────────────────────────────────
    if lead.get("linkedin"):
        score += 10
    if lead.get("org_description"):
        score += 8
    if lead.get("website"):
        score += 5
    if lead.get("headline"):
        score += 4
    if lead.get("phone"):
        score += 3

    return min(100, score)
