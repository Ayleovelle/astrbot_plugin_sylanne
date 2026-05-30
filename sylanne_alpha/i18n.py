"""Sylanne-Embodiment 国际化框架：所有用户可见字符串的多语言支持。

使用方式：
    from sylanne_alpha.i18n import t, set_language

    set_language("en")
    print(t("greeting", name="Alice"))  # Hello, Alice!

翻译文件存放在 sylanne_alpha/prompts/ 目录下，
以语言代码命名（如 zh.json、en.json）。
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from pathlib import Path

_LOCALE_DIR = Path(__file__).parent / "prompts"
_loaded: dict[str, dict] = {}
_current_lang: ContextVar[str] = ContextVar("sylanne_lang", default="zh")


def set_language(lang: str):
    _current_lang.set(lang)


def get_language() -> str:
    return _current_lang.get()


def t(key: str, lang: str | None = None, **kwargs) -> str:
    """翻译函数。支持 {placeholder} 格式化。

    lang 参数可显式指定语言，不传则使用当前上下文语言。
    """
    use_lang = lang or _current_lang.get()
    if use_lang not in _loaded:
        _load_locale(use_lang)
    text = _loaded.get(use_lang, {}).get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text


def _load_locale(lang: str):
    """加载指定语言的翻译文件。找不到时回退到 zh.json。"""
    path = _LOCALE_DIR / f"{lang}.json"
    if not path.exists():
        path = _LOCALE_DIR / "zh.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            _loaded[lang] = json.load(f)
    except Exception:
        _loaded[lang] = {}


def available_languages() -> list[str]:
    """返回可用语言列表（基于 prompts 目录下的 .json 文件）。"""
    return [p.stem for p in _LOCALE_DIR.glob("*.json")]


__all__ = [
    "set_language",
    "get_language",
    "t",
    "available_languages",
]
