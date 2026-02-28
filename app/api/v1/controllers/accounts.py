from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from app.api.dependencies import get_db_session
from app.models.email_account import EmailAccount
from app.schemas.account import AccountIn
from app.repositories.account_repository import account_repository
from app.utils.email_engine import EmailEngine

router = APIRouter()

@router.get("/")
def list_accounts(session: Session = Depends(get_db_session)):
    accs = account_repository.get_all(session)
    out = []
    for a in accs:
        out.append({
            "id": a.id,
            "email": a.email,
            "provider": a.provider,
            "display_name": a.display_name,
            "is_active": a.is_active,
            "created_at": a.created_at
        })
    return {"accounts": out}

@router.post("/", status_code=201)
def add_account(body: AccountIn, session: Session = Depends(get_db_session)):
    acc = EmailAccount(
        email=body.email.strip().lower(),
        app_password=body.app_password.strip(),
        provider=body.provider.strip().lower(),
        display_name=body.display_name.strip()
    )
    acc = account_repository.create(session, acc)
    return {"status": "added", "id": acc.id}

@router.delete("/{account_id}")
def delete_account(account_id: int, session: Session = Depends(get_db_session)):
    acc = account_repository.get(session, account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    account_repository.remove(session, account_id)
    return {"status": "deleted"}

@router.post("/{account_id}/test")
async def test_account_connection(account_id: int, session: Session = Depends(get_db_session)):
    acc = account_repository.get(session, account_id)
    if not acc:
        raise HTTPException(404, "Account not found")

    engine = EmailEngine([{
        "id": acc.id,
        "email": acc.email,
        "app_password": acc.app_password,
        "provider": acc.provider,
        "display_name": acc.display_name
    }])
    res = await engine.test_account(acc.email)
    
    if res.get("ok"):
        acc.is_active = True
    else:
        acc.is_active = False
        
    session.add(acc)
    session.commit()
    return res
