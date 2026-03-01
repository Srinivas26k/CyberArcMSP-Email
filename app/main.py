import asyncio
import logging
import os
import shutil
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

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
    logger.info("✅ CA MSP AI Outreach started (Industrial Framework)")
    yield
    logger.info("Shutting down…")

app = FastAPI(title="CA MSP AI Outreach", version="2.1.1", lifespan=lifespan)

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
