import asyncio
from typing import Optional

class CampaignState:
    def __init__(self):
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.lock = asyncio.Lock()

    def is_running(self) -> bool:
        return self.running

    def set_running(self, val: bool):
        self.running = val

campaign_state = CampaignState()
