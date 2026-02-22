from typing import Optional
from sqlmodel import Field, SQLModel, create_engine, Session

class EmailAccount(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    app_password: str
    provider_type: str = Field(description="'gmail' or 'outlook'")
    is_active: bool = Field(default=True)

class Lead(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    industry: Optional[str] = None
    location: Optional[str] = None

class CampaignState(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="lead.id")
    status: str = Field(default="pending")  # pending, contacted, replied, bounced
    last_contacted_at: Optional[str] = None
    email_account_id: Optional[int] = Field(default=None, foreign_key="emailaccount.id")
    thread_id: Optional[str] = None

sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

engine = create_engine(sqlite_url, echo=False)

def init_db():
    SQLModel.metadata.create_all(engine)
