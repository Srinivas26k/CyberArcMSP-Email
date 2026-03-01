from sqlmodel import Session, select
from typing import Optional, List
from app.repositories.base_repository import BaseRepository
from app.models.lead import Lead

class LeadRepository(BaseRepository[Lead]):
    def __init__(self):
        super().__init__(Lead)
        
    def get_by_email(self, session: Session, email: str) -> Optional[Lead]:
        return session.exec(select(Lead).where(Lead.email == email)).first()
        
    def get_pending(self, session: Session, limit: Optional[int] = None) -> List[Lead]:
        query = select(Lead).where(Lead.status == "pending")
        if limit:
            query = query.limit(limit)
        return session.exec(query).all()

lead_repository = LeadRepository()
