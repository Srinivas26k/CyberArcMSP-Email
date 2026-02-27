import asyncio
import httpx
from dotenv import load_dotenv
import os

load_dotenv()

async def test():
    APOLLO_KEY = os.environ.get("APOLLO_API_KEY")
    payload = {
        "person_titles": ["CEO"],
        "person_seniority_tags": ["c_suite", "vp", "director"],
        "person_locations": ["India"],
        "organization_locations": ["India"],
        "q_organization_industries": ["Financial Services"],
        "q_keywords": "",
        "contact_email_status": ["verified", "likely to engage"],
        "per_page": 25,
        "page": 1,
    }
    
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.apollo.io/v1/mixed_people/api_search",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "X-Api-Key": APOLLO_KEY
            },
        )
        print(r.status_code)
        print(r.text)

asyncio.run(test())
