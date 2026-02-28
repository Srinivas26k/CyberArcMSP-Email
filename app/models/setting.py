from typing import Optional
from sqlmodel import Field
from app.models.base import Base


class Setting(Base, table=True):
    """Key-value store for runtime configuration."""
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    value: str = Field(default="")
