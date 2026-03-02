"""
track.py — Email open-tracking pixel endpoint.

When an email is sent, a 1×1 transparent GIF is embedded:
  <img src="http://{host}/api/track/open/{tracking_id}" width="1" height="1">

Each GET on this endpoint increments Campaign.open_count and stamps
Campaign.opened_at on first open.  The lead status is promoted to
"opened" if it was previously "sent".

Note: For tracking to work with external recipients the app must be
reachable from the internet.  Set `public_url` in Settings to expose
a public host (e.g. via ngrok or a VPS).  Tracking still works locally
when testing with clients on the same machine.
"""
import base64
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlmodel import Session, select

from app.api.dependencies import get_db_session
from app.models.campaign import Campaign
from app.models.lead import Lead

router = APIRouter()

# 1×1 transparent GIF (43 bytes)
_PIXEL = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)
_NO_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}


@router.get("/open/{tracking_id}")
async def track_open(
    tracking_id: str,
    session: Session = Depends(get_db_session),
):
    """Record an open event and return a 1×1 transparent GIF."""
    campaign = session.exec(
        select(Campaign).where(Campaign.tracking_id == tracking_id)
    ).first()

    if campaign:
        campaign.open_count = (campaign.open_count or 0) + 1
        if not campaign.opened_at:
            campaign.opened_at = datetime.now(timezone.utc).isoformat()
            # Promote lead status: sent → opened
            lead = session.get(Lead, campaign.lead_id)
            if lead and lead.status == "sent":
                lead.status = "opened"
                session.add(lead)
        session.add(campaign)
        session.commit()

    return Response(content=_PIXEL, media_type="image/gif", headers=_NO_CACHE)
