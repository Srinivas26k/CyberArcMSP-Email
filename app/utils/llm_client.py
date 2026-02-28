"""
llm_client.py — Unified async LLM client for Groq + OpenRouter.

Strategy:
  1. Try Groq first with a model cascade (fastest + free tier).
  2. On repeated 429s or all models exhausted, fall through to OpenRouter.
  3. Exponential back-off on rate limits.
  Returns a clean dict: {"subject": "...", "bodyHtml": "..."}
"""
import asyncio
import json
import logging
import re
import time
from collections import deque
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# MODEL CASCADES
# ─────────────────────────────────────────────────────────────────────────────

GROQ_MODELS = [
    "moonshotai/kimi-k2-instruct",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
]

OPENROUTER_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
]


# ─────────────────────────────────────────────────────────────────────────────
# RATE LIMITER (sliding window)
# ─────────────────────────────────────────────────────────────────────────────

class _RateLimiter:
    def __init__(self, rpm: int):
        self.rpm = rpm
        self._window: deque = deque()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            # Drop timestamps older than 60 s
            while self._window and now - self._window[0] > 60:
                self._window.popleft()
            if len(self._window) >= self.rpm:
                wait = 61 - (now - self._window[0])
                logger.debug(f"Rate limit: sleeping {wait:.1f}s")
                await asyncio.sleep(wait)
            self._window.append(time.monotonic())


_groq_limiter = _RateLimiter(rpm=28)
_openrouter_limiter = _RateLimiter(rpm=18)
_groq_sem = asyncio.Semaphore(1)        # serialise Groq calls
_openrouter_sem = asyncio.Semaphore(1)  # serialise OpenRouter calls


# ─────────────────────────────────────────────────────────────────────────────
# JSON EXTRACTOR
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json(raw: str) -> dict:
    """Strip markdown fences, find the outermost {...}, parse JSON."""
    raw = re.sub(r"```json|```", "", raw).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in LLM output: {raw[:200]}")
    return json.loads(raw[start:end + 1])


# ─────────────────────────────────────────────────────────────────────────────
# GROQ CALLER
# ─────────────────────────────────────────────────────────────────────────────

async def _call_groq(system: str, user: str, api_key: str) -> Optional[str]:
    """Try each Groq model in cascade. Returns raw LLM text or None on total failure."""
    for model in GROQ_MODELS:
        for attempt in range(3):
            async with _groq_sem:
                await _groq_limiter.acquire()
                try:
                    async with httpx.AsyncClient(timeout=50) as client:
                        r = await client.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                            json={
                                "model": model,
                                "messages": [
                                    {"role": "system", "content": system},
                                    {"role": "user",   "content": user},
                                ],
                                "temperature": 0.65,
                                "max_tokens":  1500,
                            },
                        )
                        if r.status_code == 429:
                            body = {}
                            try:
                                body = r.json()
                            except Exception:
                                pass
                            wait_match = re.search(r"try again in (\d+(?:\.\d+)?)s", str(body))
                            wait = float(wait_match.group(1)) if wait_match else (2 ** attempt * 2)
                            wait = min(wait + 1, 30)
                            logger.warning(f"Groq 429 on {model}, sleeping {wait:.1f}s")
                            await asyncio.sleep(wait)
                            continue
                        if r.status_code == 200:
                            content = r.json()["choices"][0]["message"]["content"]
                            logger.info(f"Groq success via {model}")
                            return content
                        logger.warning(f"Groq {r.status_code} on {model}: {r.text[:120]}")
                except httpx.TimeoutException:
                    logger.warning(f"Groq timeout on {model}, attempt {attempt+1}")
                    await asyncio.sleep(2 ** attempt)
                except Exception as exc:
                    logger.warning(f"Groq error on {model}: {exc}")
                    await asyncio.sleep(2 ** attempt)
    return None  # all Groq models exhausted


# ─────────────────────────────────────────────────────────────────────────────
# OPENROUTER CALLER
# ─────────────────────────────────────────────────────────────────────────────

async def _call_openrouter(system: str, user: str, api_key: str, model: Optional[str] = None) -> str:
    """Try OpenRouter. Raises on final failure."""
    models_to_try = [model] if model else OPENROUTER_MODELS
    for m in models_to_try:
        for attempt in range(3):
            async with _openrouter_sem:
                await _openrouter_limiter.acquire()
                try:
                    async with httpx.AsyncClient(timeout=60) as client:
                        r = await client.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json",
                                "HTTP-Referer": "https://cyberarcmsp.com",
                                "X-Title": "SRV AI Outreach",
                            },
                            json={
                                "model": m,
                                "messages": [
                                    {"role": "system", "content": system},
                                    {"role": "user",   "content": user},
                                ],
                                "max_tokens": 1500,
                                "temperature": 0.65,
                            },
                        )
                        if r.status_code == 429:
                            await asyncio.sleep(2 ** attempt * 2)
                            continue
                        if r.status_code == 200:
                            content = r.json()["choices"][0]["message"]["content"]
                            logger.info(f"OpenRouter success via {m}")
                            return content
                        logger.warning(f"OpenRouter {r.status_code} on {m}: {r.text[:120]}")
                except Exception as exc:
                    logger.warning(f"OpenRouter error on {m}: {exc}")
                    await asyncio.sleep(2 ** attempt)
    raise RuntimeError("All LLM providers failed to generate a response.")


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

async def generate_email(
    system_prompt: str,
    user_prompt: str,
    groq_key: str = "",
    openrouter_key: str = "",
    preferred_provider: str = "groq",   # "groq" | "openrouter"
    openrouter_model: Optional[str] = None,
) -> dict:
    """
    Generates an email draft using the available LLM provider.

    Returns:
        dict with keys "subject" (str) and "bodyHtml" (str).

    Raises:
        RuntimeError if all providers fail.
    """
    raw: Optional[str] = None

    if preferred_provider == "openrouter" and openrouter_key:
        raw = await _call_openrouter(system_prompt, user_prompt, openrouter_key, openrouter_model)
    elif groq_key:
        raw = await _call_groq(system_prompt, user_prompt, groq_key)
        # Fallback to OpenRouter if Groq exhausted
        if raw is None and openrouter_key:
            logger.info("Groq exhausted — falling back to OpenRouter")
            raw = await _call_openrouter(system_prompt, user_prompt, openrouter_key, openrouter_model)
    elif openrouter_key:
        raw = await _call_openrouter(system_prompt, user_prompt, openrouter_key, openrouter_model)

    if raw is None:
        raise RuntimeError("No LLM API keys configured or all providers failed.")

    result = _extract_json(raw)

    # Enforce subject length cap
    if len(result.get("subject", "")) > 60:
        result["subject"] = result["subject"][:57] + "..."

    # Normalise key name (bodyHtml vs body_html)
    if "body_html" in result and "bodyHtml" not in result:
        result["bodyHtml"] = result.pop("body_html")

    return result
