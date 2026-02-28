from sqlmodel import Session, select
from typing import List
from app.repositories.base_repository import BaseRepository
from app.models.email_account import EmailAccount

class AccountRepository(BaseRepository[EmailAccount]):
    def __init__(self):
        super().__init__(EmailAccount)
        
    def get_active_accounts(self, session: Session) -> List[EmailAccount]:
        return session.exec(select(EmailAccount).where(EmailAccount.is_active == True)).all()

account_repository = AccountRepository()
