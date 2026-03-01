"""
llm_client.py — Unified async LLM client.

Supported providers: Groq, OpenRouter, OpenAI, Anthropic, Google Gemini.

Strategy:
  Providers are tried in user-defined priority order (up to 5 slots).
  Each slot specifies: provider name, api_key, and optional model override.
  Falls back to next slot on any failure.  Exponential back-off on 429s.
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
# PROVIDER REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

PROVIDER_DEFS: dict[str, dict] = {
    "groq": {
        "base_url":      "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "format":        "openai",
    },
    "openrouter": {
        "base_url":      "https://openrouter.ai/api/v1",
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",
        "format":        "openai",
        "extra_headers": {
            "HTTP-Referer": "https://srvai.io",
            "X-Title":      "SRV AI Outreach",
        },
    },
    "openai": {
        "base_url":      "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "format":        "openai",
    },
    "gemini": {
        # Google exposes an OpenAI-compatible endpoint for Gemini models
        "base_url":      "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-1.5-flash",
        "format":        "openai",
    },
    "anthropic": {
        "base_url":      "https://api.anthropic.com/v1",
        "default_model": "claude-3-5-haiku-20241022",
        "format":        "anthropic",   # different request/response shape
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# RATE LIMITERS  (one per provider, sliding window)
# ─────────────────────────────────────────────────────────────────────────────

class _RateLimiter:
    def __init__(self, rpm: int):
        self.rpm = rpm
        self._window: deque = deque()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            while self._window and now - self._window[0] > 60:
                self._window.popleft()
            if len(self._window) >= self.rpm:
                wait = 61 - (now - self._window[0])
                logger.debug(f"Rate limit: sleeping {wait:.1f}s")
                await asyncio.sleep(wait)
            self._window.append(time.monotonic())


_rate_limiters: dict[str, _RateLimiter] = {
    "groq":       _RateLimiter(rpm=28),
    "openrouter": _RateLimiter(rpm=18),
    "openai":     _RateLimiter(rpm=40),
    "gemini":     _RateLimiter(rpm=15),
    "anthropic":  _RateLimiter(rpm=15),
}

_provider_sems: dict[str, asyncio.Semaphore] = {
    k: asyncio.Semaphore(1) for k in PROVIDER_DEFS
}


# ─────────────────────────────────────────────────────────────────────────────
# JSON EXTRACTOR
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json(raw: str) -> dict:
    """Strip markdown fences, find the outermost {...}, parse JSON."""
    raw = re.sub(r"```json|```", "", raw).strip()
    start = raw.find("{")
    end   = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in LLM output: {raw[:200]}")
    return json.loads(raw[start:end + 1], strict=False)


# ─────────────────────────────────────────────────────────────────────────────
# OPENAI-COMPATIBLE CALLER  (groq / openrouter / openai / gemini)
# ─────────────────────────────────────────────────────────────────────────────

async def _call_openai_compat(
    system: str,
    user: str,
    api_key: str,
    base_url: str,
    model: str,
    extra_headers: dict | None = None,
    limiter: _RateLimiter | None = None,
    sem: asyncio.Semaphore | None = None,
) -> Optional[str]:
    """Single model call on an OpenAI-compatible endpoint. Returns text or None."""
    sem = sem or asyncio.Semaphore(1)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
        **(extra_headers or {}),
    }
    for attempt in range(3):
        async with sem:
            if limiter:
                await limiter.acquire()
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    r = await client.post(
                        f"{base_url}/chat/completions",
                        headers=headers,
                        json={
                            "model":       model,
                            "messages":    [
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
                    m = re.search(r"try again in (\d+(?:\.\d+)?)s", str(body))
                    wait = float(m.group(1)) if m else (2 ** attempt * 2)
                    wait = min(wait + 1, 30)
                    logger.warning(f"429 on {model}, sleeping {wait:.1f}s")
                    await asyncio.sleep(wait)
                    continue
                if r.status_code == 200:
                    content = r.json()["choices"][0]["message"]["content"]
                    logger.info(f"Success: {base_url} / {model}")
                    return content
                logger.warning(f"{r.status_code} on {base_url}/{model}: {r.text[:120]}")
                return None  # non-retryable (auth, quota, bad model name)
            except httpx.TimeoutException:
                logger.warning(f"Timeout on {model}, attempt {attempt + 1}")
                await asyncio.sleep(2 ** attempt)
            except Exception as exc:
                logger.warning(f"Error on {model}: {exc}")
                await asyncio.sleep(2 ** attempt)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# ANTHROPIC CALLER  (Messages API — different format)
# ─────────────────────────────────────────────────────────────────────────────

async def _call_anthropic(
    system: str,
    user: str,
    api_key: str,
    model: str,
    limiter: _RateLimiter | None = None,
    sem: asyncio.Semaphore | None = None,
) -> Optional[str]:
    sem = sem or asyncio.Semaphore(1)
    for attempt in range(3):
        async with sem:
            if limiter:
                await limiter.acquire()
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    r = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key":         api_key,
                            "anthropic-version": "2023-06-01",
                            "Content-Type":      "application/json",
                        },
                        json={
                            "model":      model,
                            "max_tokens": 1500,
                            "system":     system,
                            "messages":   [{"role": "user", "content": user}],
                        },
                    )
                if r.status_code == 429:
                    await asyncio.sleep(2 ** attempt * 2)
                    continue
                if r.status_code == 200:
                    content = r.json()["content"][0]["text"]
                    logger.info(f"Anthropic success via {model}")
                    return content
                logger.warning(f"Anthropic {r.status_code} on {model}: {r.text[:120]}")
                return None
            except Exception as exc:
                logger.warning(f"Anthropic error on {model}: {exc}")
                await asyncio.sleep(2 ** attempt)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

async def generate_email(
    system_prompt: str,
    user_prompt: str,
    providers: list[dict] | None = None,
    # ── Deprecated params kept for backward compat ──────────────────────────
    groq_key: str = "",
    openrouter_key: str = "",
    preferred_provider: str = "groq",
    openrouter_model: Optional[str] = None,
) -> dict:
    """
    Generate an email draft using the configured LLM providers in priority order.

    providers: list of dicts, each with keys:
        provider  — "groq" | "openrouter" | "openai" | "anthropic" | "gemini"
        api_key   — the API key for that provider
        model     — model name (blank = use provider default)

    Falls back to deprecated groq_key/openrouter_key params if providers is empty.

    Returns:
        dict with keys "subject" (str) and "bodyHtml" (str).
    Raises:
        RuntimeError if all providers fail or no keys are configured.
    """
    # Build effective provider list — skip slots with empty keys
    effective: list[dict] = []
    if providers:
        effective = [p for p in providers if p.get("api_key", "").strip()]

    # Backward compat: build from legacy individual key params
    if not effective:
        if preferred_provider == "openrouter" and openrouter_key:
            effective.append({"provider": "openrouter", "api_key": openrouter_key,
                               "model": openrouter_model or ""})
        if groq_key:
            effective.append({"provider": "groq", "api_key": groq_key, "model": ""})
        if openrouter_key and preferred_provider != "openrouter":
            effective.append({"provider": "openrouter", "api_key": openrouter_key,
                               "model": openrouter_model or ""})

    if not effective:
        raise RuntimeError("No LLM API keys configured or all providers failed.")

    raw: Optional[str] = None
    for slot in effective:
        pname   = (slot.get("provider") or "groq").lower()
        api_key = (slot.get("api_key")  or "").strip()
        model   = (slot.get("model")    or "").strip()
        if not api_key:
            continue

        pdef    = PROVIDER_DEFS.get(pname, PROVIDER_DEFS["openrouter"])
        model   = model or pdef["default_model"]
        limiter = _rate_limiters.get(pname)
        sem     = _provider_sems.get(pname, asyncio.Semaphore(1))

        logger.info(f"Trying provider: {pname} / {model}")

        if pdef["format"] == "anthropic":
            raw = await _call_anthropic(system_prompt, user_prompt, api_key, model, limiter, sem)
        else:
            raw = await _call_openai_compat(
                system_prompt, user_prompt, api_key,
                pdef["base_url"], model,
                pdef.get("extra_headers"),
                limiter, sem,
            )

        if raw is not None:
            break
        logger.warning(f"Provider {pname} failed, trying next slot...")

    if raw is None:
        raise RuntimeError("All configured LLM providers failed to generate a response.")

    result = _extract_json(raw)

    # Enforce subject length cap
    if len(result.get("subject", "")) > 60:
        result["subject"] = result["subject"][:57] + "..."

    # Normalise key name (bodyHtml vs body_html)
    if "body_html" in result and "bodyHtml" not in result:
        result["bodyHtml"] = result.pop("body_html")

    return result
