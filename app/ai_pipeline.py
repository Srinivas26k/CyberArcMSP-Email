from datetime import datetime
import json
import httpx
from pydantic import BaseModel

class EmailDraft(BaseModel):
    subject: str
    body_html: str

class AgentOrchestrator:
    def __init__(self, api_key: str, provider: str = "groq"):
        self.api_key = api_key
        self.provider = provider
        if provider == "groq":
            self.base_url = "https://api.groq.com/openai/v1/chat/completions"
            self.model = "llama-3.3-70b-versatile"
        else:
            self.base_url = "https://openrouter.ai/api/v1/chat/completions"
            self.model = "meta-llama/llama-3.3-70b-instruct"

    def _get_temporal_context(self) -> str:
        now = datetime.now()
        date_str = now.strftime('%B %d, %Y')
        year = now.year
        return (
            f"You are an elite B2B strategic copywriter writing in the year {year}. "
            f"Today is {date_str}. "
            f"CRITICAL RULE: Never reference 2024 or 2025 as the current or future year. "
            f"Anchor all strategic insights strictly to {year} realities."
        )

    async def generate_outreach_email(self, lead: dict) -> EmailDraft:
        temporal_context = self._get_temporal_context()
        
        system_prompt = f"""{temporal_context}
        
Your task is to generate a highly personalized cold email for a lead.
Angle Strategy: 50% Technical, 50% Risk & Compliance.
You must output ONLY valid JSON matching this schema:
{{
  "subject": "Email Subject here",
  "body_html": "HTML formatted email body here. No fluff."
}}
"""
        user_prompt = f"""Lead Details:
- Name: {lead.get('first_name', '')} {lead.get('last_name', '')}
- Role: {lead.get('role', 'Executive')}
- Company: {lead.get('company', 'Company')}
- Industry: {lead.get('industry', 'Technology')}
- Location: {lead.get('location', 'Global')}

Write the email now. Remember, relate their location/industry to {datetime.now().year} technological/regulatory realities.
"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3
        }

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(self.base_url, headers=headers, json=payload)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            
            data = json.loads(content)
            return EmailDraft(**data)
