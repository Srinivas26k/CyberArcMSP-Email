from typing import Optional
from sqlmodel import Field
from app.models.base import Base
from app.core.vault import VaultManager


class Setting(Base, table=True):
    """
    Key-value store for runtime configuration & API Keys.
    Values should be AES-256 encrypted at rest using VaultManager if sensitive.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    value: str = Field(default="")
    
    def get_decrypted_value(self) -> str:
        """Decrypts the AES-256 vault string to plaintext."""
        return VaultManager.decrypt(self.value)
        
    def set_encrypted_value(self, raw_value: str):
        """Encrypts the raw string into an AES-256 vault string."""
        self.value = VaultManager.encrypt(raw_value)
