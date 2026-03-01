import asyncio
import json

_sse_clients: list[asyncio.Queue] = []

async def broadcast(event_type: str, data: dict):
    """Push an SSE event to all connected clients."""
    payload = json.dumps({"type": event_type, **data})
    dead = []
    for q in _sse_clients:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _sse_clients.remove(q)

def add_client(queue: asyncio.Queue):
    _sse_clients.append(queue)

def remove_client(queue: asyncio.Queue):
    if queue in _sse_clients:
        _sse_clients.remove(queue)
