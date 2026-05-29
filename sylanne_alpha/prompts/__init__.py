"""多语言 prompt 模板加载器。"""
import json
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent
_cache: dict[str, dict] = {}


def load_prompts(lang: str = "zh") -> dict[str, str]:
    if lang in _cache:
        return _cache[lang]
    path = _PROMPTS_DIR / f"{lang}.json"
    if not path.exists():
        path = _PROMPTS_DIR / "zh.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _cache[lang] = data
    return data


def get_prompt(key: str, lang: str = "zh") -> str:
    prompts = load_prompts(lang)
    return prompts.get(key, f"[missing:{key}]")
