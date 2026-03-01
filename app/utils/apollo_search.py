"""
apollo_search.py — Apollo.io lead search and enrichment for SRV AI Outreach.

Two-step process (matches the working Code.gs approach):
  1. Search via mixed_people/api_search (FREE — no credits consumed)
     → returns person IDs only, names obfuscated, no emails
  2. Enrich via people/bulk_match (~1 credit per person)
     → returns full name, email, company details

Key differences from the broken version:
  • Industry uses `q_organization_keyword_tags` (keyword tag) not `q_organization_industries`
  • Employee ranges are fixed constants matching the Code.gs defaults
  • Locations are passed through directly (no transformation layer)
  • `contact_email_status` filter kept to prioritise verified emails
"""
import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

APOLLO_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_people/api_search"
APOLLO_ENRICH_URL = "https://api.apollo.io/api/v1/people/bulk_match"
ENRICH_BATCH_SIZE = 10   # Apollo hard-caps bulk_match at 10 per request


def _extract_email(person: dict) -> Optional[str]:
    """Best-effort email extraction from an enriched Apollo person record."""
    if person.get("email"):
        return person["email"]
    emails = person.get("emails") or []
    # Prefer verified
    verified = [e["email"] for e in emails
                if isinstance(e, dict) and e.get("email_status") == "verified" and e.get("email")]
    if verified:
        return verified[0]
    # Fall back to first available
    for e in emails:
        if isinstance(e, dict) and e.get("email"):
            return e["email"]
    return None


def _detect_industry(p: dict, fallback: str) -> str:
    """Mirrors Code.gs industry detection logic."""
    if fallback:
        return fallback

    org = p.get("organization") or {}
    kw = org.get("keywords") or []
    if kw:
        return kw[0].title()

    text = ((p.get("title") or "") + " " + (org.get("name") or "")).lower()
    if any(w in text for w in ("health", "medic", "pharma", "hospital")):
        return "Healthcare"
    elif any(w in text for w in ("fintech", "bank", "payment", "financ")):
        return "Financial Services"
    elif any(w in text for w in ("saas", "software")):
        return "Technology"
    elif any(w in text for w in ("manufact", "factory", "industr")):
        return "Manufacturing"
    elif any(w in text for w in ("energy", "oil", "gas")):
        return "Energy"
    return "Technology"


async def apollo_search(
    api_key: str,
    titles: list[str],
    industry: str,
    locations: list[str],
    company_sizes: list[str],
    target_count: int = 10,
) -> list[dict]:
    """
    Searches Apollo for people matching the criteria and returns enriched lead dicts.

    Steps:
      1. Search (free) → get person IDs
      2. Bulk-enrich in batches ≤ 10 → get emails + full details
      3. Deduplicate and return up to target_count leads
    """
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key,
    }

    # Employee ranges — always 100+ minimum
    default_employee_ranges = ["101,250", "251,500", "501,1000", "1001,5000", "5001,1000000"]
    employee_ranges = company_sizes if company_sizes else default_employee_ranges

    collected: list[dict] = []
    seen_emails: set[str] = set()
    credits_used: int = 0
    page = 1

    async with httpx.AsyncClient(timeout=35) as client:
        while len(collected) < target_count and page <= 20:
            needed = target_count - len(collected)
            # Search is FREE — fetch a generous pool so we can filter smartly.
            # Apollo's has_email flag tells us who has an email without spending credits.
            search_per_page = min(max(needed * 8, 25), 100)

            # ── STEP 1: Search (FREE) ─────────────────────────────────────────
            search_payload: dict = {
                "page":        page,
                "per_page":    search_per_page,
                "person_titles": titles,
                "person_seniorities": ["c_suite", "vp", "director", "manager", "owner", "founder"],
                "organization_num_employees_ranges": employee_ranges,
                "contact_email_status": ["verified", "likely to engage"],
            }

            # Industry: use q_organization_keyword_tags (matching Code.gs)
            if industry:
                search_payload["q_organization_keyword_tags"] = [industry]

            # Locations: direct list passthrough (matching Code.gs)
            if locations:
                search_payload["person_locations"] = locations

            logger.info(f"Apollo search page {page}: titles={titles}, industry={industry}, locs={locations}")

            try:
                resp = await client.post(APOLLO_SEARCH_URL, json=search_payload, headers=headers)
            except httpx.TimeoutException:
                logger.warning(f"Apollo search timeout on page {page}")
                break

            if resp.status_code == 401:
                raise RuntimeError("Apollo API key is invalid (401). Check your key in Settings.")
            if resp.status_code == 429:
                logger.warning("Apollo rate limited, waiting 5 s")
                await asyncio.sleep(5)
                continue
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Apollo search error {resp.status_code}: {resp.text[:300]}")

            people = resp.json().get("people", [])
            if not people:
                logger.info(f"Apollo returned 0 people on page {page} — stopping")
                break

            # Filter to people Apollo already knows have emails — FREE.
            # has_email is a boolean in the Apollo response; fall back to all
            # people if the field is absent (older API keys may omit it).
            people_with_email = [p for p in people if p.get("id") and p.get("has_email") is not False]
            if not people_with_email:
                # has_email absent for all — use everyone but still cap tightly
                people_with_email = [p for p in people if p.get("id")]
            logger.info(f"Page {page}: {len(people)} results, {len(people_with_email)} candidates for enrichment")

            # Enrich exactly what we still need — the outer while-loop retries
            # if enrichment misses (no email returned).  This minimises credits:
            # worst case = target_count + number_of_miss_retries.
            to_enrich = people_with_email[:needed]
            person_ids = [p["id"] for p in to_enrich]
            if not person_ids:
                page += 1
                continue

            # ── STEP 2: Bulk Enrich (costs credits) ───────────────────────────
            for batch_start in range(0, len(person_ids), ENRICH_BATCH_SIZE):
                if len(collected) >= target_count:
                    break
                batch = person_ids[batch_start:batch_start + ENRICH_BATCH_SIZE]

                # Note: Code.gs uses query param, we support both
                enrich_url = APOLLO_ENRICH_URL + "?reveal_personal_emails=true"

                try:
                    er = await client.post(
                        enrich_url,
                        json={"details": [{"id": pid} for pid in batch]},
                        headers=headers,
                    )
                except httpx.TimeoutException:
                    logger.warning("Apollo enrich timeout, skipping batch")
                    continue

                if er.status_code == 402:
                    raise RuntimeError(
                        "Apollo credit balance exhausted (402). "
                        "Add billing or reduce the number of leads."
                    )
                if er.status_code not in (200, 201):
                    logger.warning(f"Apollo enrich error {er.status_code}: {er.text[:200]}")
                    continue

                matches = er.json().get("matches", [])
                credits_used += len(batch)   # Apollo charges 1 credit per ID sent
                logger.info(f"Enrich returned {len(matches)} matches for {len(batch)} IDs")

                for p in matches:
                    if len(collected) >= target_count:
                        break

                    email = _extract_email(p)
                    if not email:
                        logger.debug(f"No email for {p.get('first_name', '?')} — skipping")
                        continue
                    if email.lower() in seen_emails:
                        logger.debug(f"Duplicate: {email}")
                        continue

                    org  = p.get("organization") or {}
                    loc  = ", ".join(filter(None, [p.get("city"), p.get("state"), p.get("country")]))
                    emp  = str(org.get("estimated_num_employees", "")) if org.get("estimated_num_employees") else ""

                    # Funding info
                    funding_events = org.get("funding_events") or []
                    latest_funding = ""
                    if funding_events:
                        fe = funding_events[0]
                        amt = fe.get("amount")
                        rnd = fe.get("series") or fe.get("round_name", "")
                        latest_funding = f"{rnd} ${amt:,}" if amt else rnd

                    # Tech stack
                    tech_stack = ", ".join((org.get("technology_names") or [])[:10])

                    seen_emails.add(email.lower())
                    collected.append({
                        # Core
                        "email":            email,
                        "first_name":       p.get("first_name") or "",
                        "last_name":        p.get("last_name") or "",
                        "role":             p.get("title") or (titles[0] if titles else ""),
                        "seniority":        p.get("seniority") or "",
                        "headline":         p.get("headline") or "",
                        "location":         loc,
                        "linkedin":         p.get("linkedin_url") or "",
                        "twitter":          p.get("twitter_url") or "",
                        "phone":            p.get("phone") or "",
                        "departments":      ", ".join(p.get("departments") or []),
                        # Company
                        "company":          org.get("name") or "",
                        "website":          org.get("website_url") or "",
                        "employees":        emp,
                        "industry":         _detect_industry(p, industry),
                        "org_industry":     org.get("industry") or "",
                        "org_founded":      str(org.get("founded_year")) if org.get("founded_year") else "",
                        "org_description":  org.get("short_description") or "",
                        "org_linkedin":     org.get("linkedin_url") or "",
                        "org_twitter":      org.get("twitter_url") or "",
                        "org_funding":      latest_funding,
                        "org_tech_stack":   tech_stack,
                        # Meta
                        "status":           "pending",
                    })
                    logger.info(f"✅ Added: {email} | {org.get('name', '?')}")

                await asyncio.sleep(0.5)

            page += 1
            await asyncio.sleep(0.8)

    logger.info(f"Apollo search complete: {len(collected)} leads collected, {credits_used} credits used")
    return collected, credits_used
