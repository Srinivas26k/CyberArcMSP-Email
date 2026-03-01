import os
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM APIs
    llm_provider: str = "groq"
    groq_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    openrouter_model: Optional[str] = None

    # Apollo.io[]
    apollo_api_key: Optional[str] = None

    # Sender Identity
    sender_name: str = "CyberArc MSP"
    sender_title: str = "Enterprise Solutions Architect"
    calendly_url: Optional[str] = None

    # Database
    app_data_dir: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    def get_o365_accounts(self) -> List[dict]:
        """Parse OUTLOOK_EMAIL_X predefined accounts from the environment"""
        accounts = []
        for i in range(1, 6):
            em = os.environ.get(f"OUTLOOK_EMAIL_{i}")
            pw = os.environ.get(f"OUTLOOK_PASS_{i}")
            nm = os.environ.get(f"OUTLOOK_NAME_{i}")
            if em and pw:
                accounts.append({
                    "email": em,
                    "password": pw,  # mapped to app_password in db
                    "name": nm or em.split("@")[0]
                })
        return accounts


settings = Settings()
