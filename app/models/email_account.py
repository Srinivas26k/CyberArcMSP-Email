from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field
from app.models.base import Base
from app.core.vault import VaultManager


class EmailAccount(Base, table=True):
    """A connected sender email account (Gmail or Outlook).
    app_password is stored AES-256 encrypted via VaultManager.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    app_password: str  # stored encrypted
    provider: str = Field(description="'gmail' or 'outlook'")
    display_name: str = Field(default="")
    is_active: bool = Field(default=True)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def get_decrypted_password(self) -> str:
        """Returns the plaintext app password (decrypts VaultManager ciphertext).
        Falls back gracefully for legacy unencrypted values already in the DB.
        """
        return VaultManager.decrypt(self.app_password)
