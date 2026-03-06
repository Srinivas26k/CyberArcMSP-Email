import asyncio
import logging
import os
import shutil
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.core import db
from app.api.v1.api import api_router
from app.core import sse

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger("app.main")

def _migrate_legacy_db_if_needed():
    target = db._DB_PATH
    if os.path.exists(target):
        return
    # Migration logic ported from legacy main.py
    target_dir = os.path.dirname(target)
    os.makedirs(target_dir, exist_ok=True)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Root dir
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(here, "database.db"),
        os.path.join(home, ".config", "CyberArc Outreach", "database.db"),
    ]
    for source in candidates:
        if source == target:
            continue
        try:
            if os.path.exists(source) and os.path.getsize(source) > 0:
                shutil.copy2(source, target)
                logger.warning("Migrated legacy database from %s to %s", source, target)
                return
        except Exception:
            pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    _migrate_legacy_db_if_needed()
    db.init_db()

    # ── Recover leads stuck in "drafting" state from a prior crash ─────────
    # If the system was killed mid-campaign, some leads may have status="drafting"
    # which prevents them from being picked up again.  Reset them to "pending".
    try:
        from sqlmodel import Session, select
        from app.models.lead import Lead
        with Session(db.engine) as session:
            stuck = session.exec(
                select(Lead).where(Lead.status == "drafting")
            ).all()
            if stuck:
                for lead in stuck:
                    lead.status = "pending"
                    session.add(lead)
                session.commit()
                logger.info("♻️  Recovered %d stuck 'drafting' lead(s) → pending", len(stuck))
    except Exception as exc:
        logger.warning("Could not recover stuck leads: %s", exc)

    logger.info("✅ CA MSP AI Outreach started (Industrial Framework)")

    # Background task: process sequence follow-ups every 10 minutes
    async def _sequence_scheduler():
        while True:
            await asyncio.sleep(600)  # 10 minutes
            try:
                from app.services.sequence_service import process_due_enrollments
                sent = await process_due_enrollments()
                if sent:
                    await sse.broadcast("stat", {"refresh": True})
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Sequence scheduler error: %s", exc)

    sched_task = asyncio.create_task(_sequence_scheduler())
    yield
    sched_task.cancel()
    try:
        await sched_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutting down…")

app = FastAPI(title="CA MSP AI Outreach", version="2.1.1", lifespan=lifespan)

# ── No-cache middleware for static assets ─────────────────────────────────────
# Prevents Electron/Chromium from caching JS/CSS/HTML between app launches.
# Without this, a previously cached broken JS file (e.g. with a SyntaxError)
# can persist across restarts and silently break page functionality.
class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.endswith(('.js', '.css', '.html')) or path in ('/', ''):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
        return response

app.add_middleware(NoCacheStaticMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8008", "http://localhost:8008",
        "http://127.0.0.1:8002", "http://localhost:8002",
        "http://localhost:5173",  "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root level routes inside API v1
app.include_router(api_router, prefix="/api")

@app.get("/api/stream")
async def sse_stream():
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    sse.add_client(queue)

    async def generator():
        yield "data: {\"type\": \"connected\"}\n\n"
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=25)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            sse.remove_client(queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI_DIR = os.path.join(_here, "ui")

if os.path.isdir(_UI_DIR):
    app.mount("/", StaticFiles(directory=_UI_DIR, html=True), name="frontend")
else:
    logger.warning("ui/ directory not found — frontend will not be served.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8002, reload=True)
