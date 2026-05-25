from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .body import SCHEMA_VERSION
from .kernel import AlphaKernel


class AlphaRuntime:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def load(
        self, session_key: str, legacy: dict[str, Any] | None = None
    ) -> AlphaKernel:
        path = self._path(session_key)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.root.mkdir(parents=True, exist_ok=True)
                path.replace(path.with_suffix(path.suffix + ".damaged"))
                recovered = AlphaKernel.boot(session_key=session_key, legacy=legacy)
                self.save(recovered)
                return recovered
            if data.get("schema_version") == SCHEMA_VERSION:
                return AlphaKernel.restore(data)
            return AlphaKernel.boot(session_key=session_key, legacy=data)
        return AlphaKernel.boot(session_key=session_key, legacy=legacy)

    def save(self, kernel: AlphaKernel) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(kernel.session_key)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(kernel.snapshot(), ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        try:
            os.replace(tmp, path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise

    def reset(self, session_key: str) -> AlphaKernel:
        kernel = AlphaKernel.boot(session_key=session_key)
        self.save(kernel)
        return kernel

    def export_all(self) -> dict[str, Any]:
        sessions: dict[str, Any] = {}
        recovered: list[str] = []
        if not self.root.exists():
            return {
                "schema_version": SCHEMA_VERSION,
                "sessions": sessions,
                "recovered": recovered,
            }
        for path in self.root.glob("*.alpha.json"):
            session_key = path.name[: -len(".alpha.json")]
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                recovered.append(session_key)
                continue
            sessions[session_key] = data
        for path in self.root.glob("*.alpha.json.damaged"):
            recovered.append(path.name[: -len(".alpha.json.damaged")])
        return {
            "schema_version": SCHEMA_VERSION,
            "sessions": sessions,
            "recovered": sorted(set(recovered)),
        }

    def _path(self, session_key: str) -> Path:
        safe = (
            "".join(
                ch if ch.isalnum() or ch in {"-", "_", "."} else "_"
                for ch in session_key
            )
            or "default"
        )
        return self.root / f"{safe}.alpha.json"

    def save_buffer(self, session_key: str, buffer_data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._buffer_path(session_key)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(buffer_data, ensure_ascii=False), encoding="utf-8")
        try:
            os.replace(tmp, path)
        except OSError:
            tmp.unlink(missing_ok=True)

    def load_buffer(self, session_key: str) -> dict[str, Any] | None:
        path = self._buffer_path(session_key)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
        return None

    def _buffer_path(self, session_key: str) -> Path:
        safe = (
            "".join(
                ch if ch.isalnum() or ch in {"-", "_", "."} else "_"
                for ch in session_key
            )
            or "default"
        )
        return self.root / f"{safe}.buffer.json"
