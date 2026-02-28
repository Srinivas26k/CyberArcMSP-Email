from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from app.api.dependencies import get_db_session
from app.models.reply import Reply
from app.repositories.account_repository import account_repository
from app.utils.email_engine import EmailEngine
from app.core.sse import broadcast

router = APIRouter()

@router.post("/check")
async def check_replies(session: Session = Depends(get_db_session)):
    accs = account_repository.get_active_accounts(session)
    engine = EmailEngine(
        [{"id": a.id, "email": a.email, "app_password": a.app_password,
          "provider": a.provider, "display_name": a.display_name} for a in accs]
    )
    
    replies_found = await engine.check_all_replies()
    saved = 0
    for r in replies_found:
        existing = session.exec(
            select(Reply).where(
                Reply.from_email == r["from_email"],
                Reply.subject == r["subject"]
            )
        ).first()
        if not existing:
            reply = Reply(**r)
            session.add(reply)
            saved += 1
            await broadcast("reply", {"message": f"New reply from {r['from_email']}"})
    
    session.commit()
    if saved > 0:
        await broadcast("stat", {"refresh": True})
        
    return {"status": "checked", "new_replies": saved}

@router.get("/")
def list_replies(session: Session = Depends(get_db_session)):
    replies = session.exec(select(Reply)).all()
    return {"replies": [dict(r) for r in replies]}
