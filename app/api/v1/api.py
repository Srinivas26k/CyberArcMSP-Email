from fastapi import APIRouter
from app.api.v1.controllers import (
    health,
    accounts,
    leads,
    campaigns,
    replies,
    settings,
    database
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(replies.router, prefix="/replies", tags=["replies"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(database.router, prefix="/db", tags=["database"])
