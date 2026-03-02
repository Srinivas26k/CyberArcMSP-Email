"""
unsubscribe.py — One-click unsubscribe endpoint.

Each Lead gets a unique token (Lead.unsubscribe_token).
The unsubscribe link injected in every email footer points to:
  GET /api/unsubscribe/{token}

On success: Lead.is_unsubscribed = True, Lead.status = "unsubscribed".
The lead is then skipped by all future campaign sends.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from app.api.dependencies import get_db_session
from app.models.lead import Lead

router = APIRouter()

_UNSUB_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Unsubscribed</title>
  <style>
    body{font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
         background:#f0f2f5;margin:0;padding:40px 16px;color:#333;}
    .card{max-width:480px;margin:60px auto;background:#fff;border-radius:10px;
          padding:48px 40px;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.08);}
    .icon{font-size:48px;margin-bottom:16px;}
    h1{font-size:24px;margin:0 0 12px;color:#27ae60;}
    p{color:#666;line-height:1.6;margin:0;}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✅</div>
    <h1>You've been unsubscribed</h1>
    <p>Your email address has been removed from our mailing list.<br>
       You won't receive any further emails from us.</p>
  </div>
</body>
</html>"""

_INVALID_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Invalid Link</title>
  <style>
    body{font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
         background:#f0f2f5;margin:0;padding:40px 16px;color:#333;}
    .card{max-width:480px;margin:60px auto;background:#fff;border-radius:10px;
          padding:48px 40px;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.08);}
    h1{font-size:22px;margin:0 0 12px;color:#e74c3c;}
    p{color:#666;line-height:1.6;margin:0;}
  </style>
</head>
<body>
  <div class="card">
    <h1>Link expired or invalid</h1>
    <p>Please contact us directly if you wish to be removed from our list.</p>
  </div>
</body>
</html>"""


@router.get("/{token}", response_class=HTMLResponse)
async def unsubscribe(token: str, session: Session = Depends(get_db_session)):
    """Process a one-click unsubscribe request."""
    lead = session.exec(
        select(Lead).where(Lead.unsubscribe_token == token)
    ).first()

    if not lead:
        return HTMLResponse(_INVALID_HTML, status_code=404)

    lead.is_unsubscribed = True
    lead.status = "unsubscribed"
    session.add(lead)
    session.commit()
    return HTMLResponse(_UNSUB_HTML)
