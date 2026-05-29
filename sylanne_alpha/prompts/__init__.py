"""多语言 prompt 模板加载器——委托给 i18n 模块。

保留此接口以兼容直接 import prompts 的代码。
底层实现统一由 i18n.py 管理。
"""

from sylanne_alpha.i18n import t


def load_prompts(lang: str = "zh") -> dict[str, str]:
    from sylanne_alpha.i18n import _load_locale, _loaded

    if lang not in _loaded:
        _load_locale(lang)
    return _loaded.get(lang, {})


def get_prompt(key: str, lang: str = "zh") -> str:
    return t(key, lang=lang)
