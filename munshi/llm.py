"""Minimal OpenAI-compatible JSON chat client (Groq by default) with retries."""

import asyncio
import json
import logging
import re

import httpx

from . import config

log = logging.getLogger("munshi.llm")


class LLMError(RuntimeError):
    pass


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise LLMError("no JSON object in model output")
    return json.loads(text[start:end + 1])


async def chat_json(system: str, user: str, attempts: int = 3, temperature: float = 0.1) -> dict:
    if not config.LLM_API_KEY:
        raise LLMError("LLM_API_KEY not set")
    body = {
        "model": config.LLM_MODEL,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    headers = {"Authorization": f"Bearer {config.LLM_API_KEY}"}
    last = None
    async with httpx.AsyncClient(base_url=config.LLM_BASE_URL, timeout=60) as http:
        for i in range(attempts):
            try:
                r = await http.post("/chat/completions", json=body, headers=headers)
                if r.status_code == 429 or r.status_code >= 500:
                    raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
                if r.status_code == 400 and "response_format" in body:
                    # Some models reject json mode; fall back to prompt-only JSON.
                    body.pop("response_format")
                    raise LLMError(f"HTTP 400, retrying without json mode: {r.text[:200]}")
                r.raise_for_status()
                return _extract_json(r.json()["choices"][0]["message"]["content"])
            except (httpx.HTTPError, LLMError, json.JSONDecodeError, KeyError) as e:
                last = e
                log.warning("LLM attempt %d failed: %s", i + 1, e)
                await asyncio.sleep(1.5 * (i + 1))
    raise LLMError(str(last))
