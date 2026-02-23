"""
apollo_search.py — Apollo.io lead search and enrichment for SRV AI Outreach.

Fixes vs the original Code.gs:
  • Uses correct v1 endpoint path
  • Enriches in batches of ≤ 10 to avoid RECORD_LIMIT_EXCEEDED
  • Async-native (compatible with FastAPI background tasks)
"""
import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

APOLLO_SEARCH_URL  = "https://api.apollo.io/api/v1/mixed_people/api_search"
APOLLO_ENRICH_URL  = "https://api.apollo.io/api/v1/people/bulk_match"
ENRICH_BATCH_SIZE  = 10   # hard cap to avoid RECORD_LIMIT_EXCEEDED

# Apollo industry slug mapping (user-friendly → Apollo keyword)
INDUSTRY_MAP: dict[str, str] = {
    "banking":       "Financial Services",
    "bank":          "Financial Services",
    "bfsi":          "Financial Services",
    "finance":       "Financial Services",
    "fintech":       "Financial Services",
    "insurance":     "Insurance",
    "healthcare":    "Hospital & Health Care",
    "health":        "Hospital & Health Care",
    "pharma":        "Pharmaceuticals",
    "saas":          "Computer Software",
    "software":      "Computer Software",
    "tech":          "Information Technology and Services",
    "technology":    "Information Technology and Services",
    "it":            "Information Technology and Services",
    "manufacturing": "Mechanical or Industrial Engineering",
    "energy":        "Oil & Energy",
    "oil":           "Oil & Energy",
    "gas":           "Oil & Energy",
    "telecom":       "Telecommunications",
    "retail":        "Retail",
    "education":     "Education Management",
    "logistics":     "Logistics and Supply Chain",
    "construction":  "Construction",
    "real estate":   "Real Estate",
    "media":         "Media Production",
    "government":    "Government Administration",
}


def _normalise_locations(locs: list[str]) -> list[str]:
    city_country = {
        "mumbai": "India", "delhi": "India", "bangalore": "India",
        "hyderabad": "India", "london": "United Kingdom", "dubai": "UAE",
        "new york": "United States", "los angeles": "United States",
        "toronto": "Canada", "sydney": "Australia", "singapore": "Singapore",
    }
    result: list[str] = []
    for loc in locs:
        loc = loc.strip().title()
        if loc not in result:
            result.append(loc)
        extra = city_country.get(loc.lower())
        if extra and extra not in result:
            result.append(extra)
    return result


def _extract_email(person: dict) -> Optional[str]:
    """Best-effort email extraction from an Apollo person record."""
    if person.get("email"):
        return person["email"]
    emails = person.get("emails") or []
    verified = [e["email"] for e in emails if isinstance(e, dict) and e.get("email_status") == "verified"]
    if verified:
        return verified[0]
    if emails:
        first = emails[0]
        return first.get("email") if isinstance(first, dict) else None
    return None


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
      1. Search (free, no credits) to get person IDs
      2. Bulk-enrich in batches ≤ 10 (costs 1 credit each) to get emails
      3. Deduplicate and return
    """
    mapped_industry = INDUSTRY_MAP.get(industry.lower().strip(), industry)
    norm_locs = _normalise_locations(locations)
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key,
    }

    collected: list[dict] = []
    seen_emails: set[str] = set()
    page = 1

    async with httpx.AsyncClient(timeout=35) as client:
        while len(collected) < target_count and page <= 20:
            # ── STEP 1: Search ────────────────────────────────────────────────
            needed    = target_count - len(collected)
            per_page  = min(needed + 5, ENRICH_BATCH_SIZE)  # small buffer

            search_payload: dict = {
                "page":          page,
                "per_page":      per_page,
                "person_titles": titles,
                "person_seniorities": ["c_suite", "vp", "director", "manager", "owner", "founder"],
                "contact_email_status": ["verified", "likely to engage"],
            }
            if company_sizes:
                search_payload["organization_num_employees_ranges"] = company_sizes
            if mapped_industry:
                search_payload["q_organization_industries"] = [mapped_industry]
            if norm_locs:
                search_payload["person_locations"] = norm_locs

            try:
                resp = await client.post(APOLLO_SEARCH_URL, json=search_payload, headers=headers)
            except httpx.TimeoutException:
                logger.warning(f"Apollo search timeout on page {page}")
                break

            if resp.status_code == 429:
                logger.warning("Apollo rate limited, waiting 5s")
                await asyncio.sleep(5)
                continue
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Apollo search error {resp.status_code}: {resp.text[:300]}")

            people = resp.json().get("people", [])
            if not people:
                logger.info(f"Apollo returned 0 people on page {page} — stopping")
                break

            # ── STEP 2: Bulk Enrich (in safe batches) ────────────────────────
            person_ids = [p["id"] for p in people if p.get("id")]

            for batch_start in range(0, len(person_ids), ENRICH_BATCH_SIZE):
                if len(collected) >= target_count:
                    break
                batch = person_ids[batch_start:batch_start + ENRICH_BATCH_SIZE]
                enrich_payload = {
                    "details":              [{"id": pid} for pid in batch],
                    "reveal_personal_emails": True,
                }
                try:
                    er = await client.post(APOLLO_ENRICH_URL, json=enrich_payload, headers=headers)
                except httpx.TimeoutException:
                    logger.warning("Apollo enrich timeout, skipping batch")
                    continue

                if er.status_code == 402:
                    raise RuntimeError("Apollo credit balance exhausted (402).")
                if er.status_code not in (200, 201):
                    logger.warning(f"Apollo enrich error {er.status_code}: {er.text[:200]}")
                    continue

                matches = er.json().get("matches", [])
                for p in matches:
                    if len(collected) >= target_count:
                        break
                    email = _extract_email(p)
                    if not email or email.lower() in seen_emails:
                        continue

                    org = p.get("organization") or {}
                    loc = ", ".join(filter(None, [p.get("city"), p.get("state"), p.get("country")]))

                    # Attempt to detect industry from org keywords if not supplied
                    detected_industry = industry or ""
                    if not detected_industry:
                        kw = org.get("keywords") or []
                        text = (p.get("title", "") + " " + org.get("name", "")).lower()
                        if kw:
                            detected_industry = kw[0].title()
                        elif "health" in text or "medic" in text:
                            detected_industry = "Healthcare"
                        elif "bank" in text or "financ" in text:
                            detected_industry = "Financial Services"
                        elif "saas" in text or "software" in text:
                            detected_industry = "Technology"
                        else:
                            detected_industry = "Technology"

                    seen_emails.add(email.lower())
                    collected.append({
                        "email":      email,
                        "first_name": p.get("first_name", ""),
                        "last_name":  p.get("last_name", ""),
                        "company":    org.get("name", ""),
                        "role":       p.get("title", titles[0] if titles else ""),
                        "website":    org.get("website_url", ""),
                        "linkedin":   p.get("linkedin_url", ""),
                        "location":   loc,
                        "seniority":  p.get("seniority", ""),
                        "employees":  str(org.get("estimated_num_employees", "")),
                        "industry":   detected_industry,
                        "status":     "pending",
                    })

                await asyncio.sleep(0.5)   # be polite between enrich batches

            page += 1
            await asyncio.sleep(0.8)   # polite paging delay

    logger.info(f"Apollo search complete: {len(collected)} leads collected")
    return collected
