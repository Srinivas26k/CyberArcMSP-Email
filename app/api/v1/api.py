from fastapi import APIRouter
from app.api.v1.controllers.health import router as health_router
from app.api.v1.controllers.accounts import router as accounts_router
from app.api.v1.controllers.leads import router as leads_router
from app.api.v1.controllers.campaigns import router as campaigns_router
from app.api.v1.controllers.replies import router as replies_router
from app.api.v1.controllers.settings import router as settings_router
from app.api.v1.controllers.database import router as database_router
from app.api.v1.controllers.setup import router as setup_router
from app.api.v1.controllers.track import router as track_router
from app.api.v1.controllers.unsubscribe import router as unsubscribe_router
from app.api.v1.controllers.sequences import router as sequences_router

api_router = APIRouter()

api_router.include_router(health_router,      prefix="/health",      tags=["health"])
api_router.include_router(settings_router,    prefix="/settings",    tags=["settings"])
api_router.include_router(setup_router,       prefix="/setup",       tags=["setup"])
api_router.include_router(campaigns_router,   prefix="/campaigns",   tags=["campaigns"])
api_router.include_router(leads_router,       prefix="/leads",       tags=["leads"])
api_router.include_router(accounts_router,    prefix="/accounts",    tags=["accounts"])
api_router.include_router(database_router,    prefix="/database",    tags=["database"])
api_router.include_router(replies_router,     prefix="/replies",     tags=["replies"])
api_router.include_router(track_router,       prefix="/track",       tags=["tracking"])
api_router.include_router(unsubscribe_router, prefix="/unsubscribe", tags=["unsubscribe"])
api_router.include_router(sequences_router,   prefix="/sequences",   tags=["sequences"])
