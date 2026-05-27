"""文件持久化运行时模块。

负责 AlphaKernel 状态的磁盘读写，使用 .alpha.json 文件格式。
写入采用原子操作（先写临时文件 + fsync，再 os.replace），确保断电/崩溃
时不会损坏已有数据。同时提供对话缓冲区（buffer）的独立文件持久化。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .body import SCHEMA_VERSION
from .kernel import AlphaKernel


class AlphaRuntime:
    """AlphaKernel 的文件持久化运行时。

    每个 session 对应一个 .alpha.json 文件，存储在 root 目录下。
    提供 load/save/reset/export_all 等完整的生命周期管理方法。
    """

    def __init__(self, root: str | Path):
        """初始化运行时，指定持久化根目录。

        Args:
            root: 存储 .alpha.json 文件的根目录路径。
        """
        self.root = Path(root)

    def load(
        self, session_key: str, legacy: dict[str, Any] | None = None
    ) -> AlphaKernel:
        """加载指定 session 的 kernel 状态。

        加载逻辑：
        1. 文件存在且 JSON 合法 → 检查 schema_version 决定 restore 或 boot(legacy)
        2. 文件存在但 JSON 损坏 → 重命名为 .damaged 后全新 boot
        3. 文件不存在 → 全新 boot

        Args:
            session_key: 会话标识。
            legacy: 旧版数据，用于 schema 迁移时的兼容启动。

        Returns:
            恢复或新建的 AlphaKernel 实例。
        """
        path = self._path(session_key)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                # JSON 损坏：保留损坏文件用于事后诊断，然后重新启动
                self.root.mkdir(parents=True, exist_ok=True)
                path.replace(path.with_suffix(path.suffix + ".damaged"))
                recovered = AlphaKernel.boot(session_key=session_key, legacy=legacy)
                self.save(recovered)
                return recovered
            if data.get("schema_version") == SCHEMA_VERSION:
                return AlphaKernel.restore(data)
            # schema 版本不匹配：将旧数据作为 legacy 传入，由 kernel 负责迁移
            return AlphaKernel.boot(session_key=session_key, legacy=data)
        return AlphaKernel.boot(session_key=session_key, legacy=legacy)

    def save(self, kernel: AlphaKernel) -> None:
        """原子写入 kernel 快照到磁盘。

        写入流程：先写 .tmp 临时文件 → fsync 确保数据落盘 → os.replace 原子替换。
        若 replace 失败则清理临时文件并向上抛出异常。

        Args:
            kernel: 要持久化的 AlphaKernel 实例。
        """
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(kernel.session_key)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    kernel.snapshot(), ensure_ascii=False, sort_keys=True, indent=2
                )
            )
            f.flush()
            os.fsync(f.fileno())  # 确保数据从 OS 缓冲区刷到物理磁盘
        try:
            os.replace(tmp, path)  # 原子替换，不会出现半写状态
        except OSError:
            tmp.unlink(missing_ok=True)
            raise

    def reset(self, session_key: str) -> AlphaKernel:
        """重置指定 session：创建全新 kernel 并立即持久化。

        Args:
            session_key: 会话标识。

        Returns:
            全新启动的 AlphaKernel 实例。
        """
        kernel = AlphaKernel.boot(session_key=session_key)
        self.save(kernel)
        return kernel

    def export_all(self) -> dict[str, Any]:
        """导出所有 session 的持久化数据，用于调试/迁移。

        Returns:
            包含 schema_version、sessions（正常数据）、recovered（损坏文件列表）的字典。
        """
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
        """将 session_key 转换为文件系统安全的 .alpha.json 路径。"""
        safe = (
            "".join(
                ch if ch.isalnum() or ch in {"-", "_", "."} else "_"
                for ch in session_key
            )
            or "default"
        )
        return self.root / f"{safe}.alpha.json"

    def save_buffer(self, session_key: str, buffer_data: dict[str, Any]) -> None:
        """原子写入对话缓冲区数据到独立的 .buffer.json 文件。

        Args:
            session_key: 会话标识。
            buffer_data: 缓冲区序列化字典。
        """
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._buffer_path(session_key)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(buffer_data, ensure_ascii=False))
            f.flush()
            os.fsync(f.fileno())
        try:
            os.replace(tmp, path)
        except OSError:
            tmp.unlink(missing_ok=True)

    def load_buffer(self, session_key: str) -> dict[str, Any] | None:
        """加载对话缓冲区数据。

        Args:
            session_key: 会话标识。

        Returns:
            缓冲区字典，文件不存在或解析失败时返回 None。
        """
        path = self._buffer_path(session_key)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
        return None

    def _buffer_path(self, session_key: str) -> Path:
        """将 session_key 转换为文件系统安全的 .buffer.json 路径。"""
        safe = (
            "".join(
                ch if ch.isalnum() or ch in {"-", "_", "."} else "_"
                for ch in session_key
            )
            or "default"
        )
        return self.root / f"{safe}.buffer.json"
