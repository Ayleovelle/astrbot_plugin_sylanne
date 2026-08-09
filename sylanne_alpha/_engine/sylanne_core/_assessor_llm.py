"""Build a zero-dependency assessor LLM callback from a config block.

The engine takes an ``async (system, user) -> str`` callback for semantic
assessment. When the shared config file carries an ``assessor_model`` block, this
turns it into such a callback against any OpenAI-compatible ``/chat/completions``
endpoint, using only the standard library (urllib + ``asyncio.to_thread``), so the
lite tier stays dependency-free and the user can point the assessor at a small,
cheap model without touching code.

If you would rather route assessment through your host framework's own provider,
pass your own ``assessor_llm`` to ``SylanneEngine`` and this builder is not used.
A block missing ``api_base`` or ``model`` yields ``None``, and the engine then
falls back to the main llm.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.request
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("sylanne_core")

LLMFn = Callable[[str, str], Awaitable[str]]

_DEFAULT_TIMEOUT = 30.0


def _resolve_env(value: str) -> str:
    """Expand a ``${VAR}`` reference from the environment; pass through otherwise.

    Lets the api_key live in an environment variable instead of plaintext in the
    config file under data_dir.
    """
    if value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


def build_from_config(block: dict[str, Any] | None) -> LLMFn | None:
    """Return an assessor callback for an OpenAI-compatible endpoint.

    Returns ``None`` when ``block`` is missing the required ``api_base``/``model``
    so the caller can fall back to the main llm.
    """
    if not isinstance(block, dict):
        return None
    api_base = str(block.get("api_base") or "").rstrip("/")
    model = str(block.get("model") or "")
    api_key = _resolve_env(str(block.get("api_key") or ""))
    if not api_base or not model:
        logger.warning("assessor_model block missing api_base/model; falling back to main llm")
        return None
    raw_timeout = block.get("timeout", _DEFAULT_TIMEOUT)
    try:
        timeout = float(raw_timeout)
    except (TypeError, ValueError):
        logger.warning(
            "assessor_model timeout %r is not a number; using default %ss",
            raw_timeout,
            _DEFAULT_TIMEOUT,
        )
        timeout = _DEFAULT_TIMEOUT
    url = f"{api_base}/chat/completions"

    async def assessor(system: str, user: str) -> str:
        def _blocking() -> str:
            body = json.dumps(
                {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0,
                }
            ).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read()
            except Exception as exc:
                logger.warning("assessor llm request to %s failed: %s", url, exc)
                raise
            try:
                payload = json.loads(raw.decode("utf-8"))
                return str(payload["choices"][0]["message"]["content"])
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                logger.warning(
                    "assessor llm response from %s unparseable: %s (body %.200r)", url, exc, raw
                )
                raise

        return await asyncio.to_thread(_blocking)

    return assessor
