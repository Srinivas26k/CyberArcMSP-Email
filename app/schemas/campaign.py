from typing import Optional, List
from pydantic import BaseModel

class DraftRequest(BaseModel):
    lead: dict
    account_id: Optional[int] = None   # None -> pick first active account

class CampaignRequest(BaseModel):
    strategy:          str = "round_robin"   # round_robin | parallel | batch_count
    batch_size:        int = 5               # for batch_count
    daily_limit:       int = 20
    delay_seconds:     int = 65
    lead_ids:          List[int] = []        # empty = all pending
    active_account_id: Optional[int] = None  # if set, use only this account
