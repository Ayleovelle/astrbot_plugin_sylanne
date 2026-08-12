from __future__ import annotations

from types import SimpleNamespace

import pytest

from sylanne_alpha import webui_server


class _Logger:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def info(self, message: str, *args: object) -> None:
        self.messages.append(("info", message % args if args else message))

    def debug(self, message: str, *args: object) -> None:
        self.messages.append(("debug", message % args if args else message))

    def warning(self, message: str, *args: object) -> None:
        self.messages.append(("warning", message % args if args else message))


class _Plugin:
    def __init__(self) -> None:
        self._config: dict[str, object] = {}
        self._webui_runtime_id = "runtime-v1"
        self._background_tasks: list[object] = []
        self.logger = _Logger()

    def _cfg_bool(self, _key: str, _default: bool = False) -> bool:
        return True

    def _cfg(self, _key: str, default: object = None) -> object:
        return default

    def _cfg_int(self, _key: str, default: int = 0) -> int:
        return default


def test_webui_lifecycle_uses_its_canonical_plugin_owner(monkeypatch) -> None:
    plugin = _Plugin()
    lifecycle = webui_server.WebUILifecycle(plugin)
    started: list[object] = []
    published: list[object] = []

    monkeypatch.setattr(webui_server, "_ensure_token", lambda _config: "secret")
    monkeypatch.setattr(
        webui_server,
        "start_webui_background",
        lambda owner, **_kwargs: started.append(owner),
    )
    monkeypatch.setattr(lifecycle, "publish_active_plugin", lambda: published.append(plugin))
    monkeypatch.setattr(
        lifecycle,
        "_current_webui_module_ref",
        lambda: SimpleNamespace(_server_task=None, _httpd_thread=None),
    )

    lifecycle.start_if_enabled()

    assert started == [plugin]
    assert published == [plugin]
    assert lifecycle.runtime_info()["runtime_id"] == "runtime-v1"


@pytest.mark.asyncio
async def test_webui_lifecycle_takeover_uses_plugin_config_and_logger(monkeypatch) -> None:
    plugin = _Plugin()
    lifecycle = webui_server.WebUILifecycle(plugin)
    restarted: list[bool] = []

    async def _stop_stale_server_modules(*, include_current: bool = False) -> list[str]:
        assert include_current is True
        return ["old-listener"]

    async def _no_wait(_delay: float) -> None:
        return None

    monkeypatch.setattr(lifecycle, "stop_stale_server_modules", _stop_stale_server_modules)
    monkeypatch.setattr(lifecycle, "start_if_enabled", lambda: restarted.append(True))
    monkeypatch.setattr(webui_server.asyncio, "sleep", _no_wait)

    lifecycle.schedule_listener_takeover()
    assert len(plugin._background_tasks) == 1
    await plugin._background_tasks[0]

    assert restarted == [True]
    assert any("old-listener" in message for _level, message in plugin.logger.messages)
