"""Load engine configuration from a shared file in the data directory.

Putting config in ``<data_dir>/sylanne.config.json`` gives users ONE stable place
to edit settings, independent of which plugin/copy happens to own the engine. The
engine self-reads it when no ``config`` is passed in code, so multiple plugins can
all call ``SylanneEngine.shared(data_dir)`` and get the same, user-controlled
configuration without threading a ``SylanneConfig`` through every call site.

File shape (every key optional)::

    {
        "mode": "lite",
        "assessor_enabled": true,
        "assessor_model": {
            "api_base": "https://api.deepseek.com/v1",
            "api_key": "${SYLANNE_ASSESSOR_KEY}",
            "model": "deepseek-chat"
        }
    }

Top-level keys that match a ``SylanneConfig`` field configure the engine; unknown
keys are ignored (forward-compatible). The ``assessor_model`` block is pulled out
separately and turned into a small dedicated assessor llm (see ``_assessor_llm``);
without it, assessment falls back to the main llm.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from pathlib import Path
from typing import Any

from .config import SylanneConfig

logger = logging.getLogger("sylanne_core")

CONFIG_FILENAME = "sylanne.config.json"


def load_config(data_dir: str | Path) -> tuple[SylanneConfig, dict[str, Any] | None]:
    """Read ``<data_dir>/sylanne.config.json`` into a config + assessor block.

    Returns ``(config, assessor_model_block)``. A missing, unreadable, or invalid
    file falls back to ``SylanneConfig()`` defaults so the engine always starts;
    the problem is logged, never raised.
    """
    path = Path(data_dir) / CONFIG_FILENAME
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return SylanneConfig(), None
    except (OSError, ValueError) as exc:
        logger.warning("ignoring unreadable %s (%s); using defaults", path, exc)
        return SylanneConfig(), None

    if not isinstance(data, dict):
        logger.warning("ignoring %s: top-level JSON must be an object; using defaults", path)
        return SylanneConfig(), None

    assessor = data.get("assessor_model")
    if not isinstance(assessor, dict):
        assessor = None

    known = {f.name for f in dataclasses.fields(SylanneConfig)}
    kwargs = {k: v for k, v in data.items() if k in known}
    try:
        cfg = SylanneConfig(**kwargs)
    except (TypeError, ValueError) as exc:
        logger.warning("invalid config in %s (%s); using defaults", path, exc)
        return SylanneConfig(), None
    return cfg, assessor


# A starter file dropped into a fresh data_dir so users have something to edit.
# Values mirror SylanneConfig defaults; the ``_comment`` key is ignored on load.
_DEFAULT_CONFIG_TEMPLATE: dict[str, Any] = {
    "_comment": (
        "Sylanne engine config — edit and restart. Top-level keys mirror "
        "SylanneConfig (mode / assessor_enabled / locale / ...). To route emotional "
        'assessment to a small, cheap model, add an "assessor_model" block: '
        '{"api_base": "https://api.deepseek.com/v1", "api_key": '
        '"${SYLANNE_ASSESSOR_KEY}", "model": "deepseek-chat"}. Prefer ${ENV_VAR} for '
        "api_key and do not commit secrets. Without an assessor_model, assessment "
        "uses the main llm."
    ),
    "mode": "lite",
    "assessor_enabled": True,
}


def write_default_config(data_dir: str | Path) -> bool:
    """Drop a starter ``sylanne.config.json`` into ``data_dir`` if none exists.

    Best-effort: returns True if a template was written, False if a file already
    existed or the directory is not writable (a read-only install simply runs on
    defaults). Never overwrites a user's file.
    """
    path = Path(data_dir) / CONFIG_FILENAME
    if path.exists():
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create ("x") closes the check-then-write race: if another
        # process created the file in between, this raises and we report False.
        with open(path, "x", encoding="utf-8") as f:
            json.dump(_DEFAULT_CONFIG_TEMPLATE, f, ensure_ascii=False, indent=2)
    except OSError:
        return False
    return True
