"""文件持久化运行时模块。

负责 AlphaKernel 状态的磁盘读写，使用 .alpha.json 文件格式。
写入采用原子操作（先写临时文件 + fsync，再 os.replace），确保断电/崩溃
时不会损坏已有数据。同时提供对话缓冲区（buffer）的独立文件持久化。

包含状态一致性自检守护（Item 83），定期检查内部状态合法性并自动修正。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .body import SCHEMA_VERSION
from .kernel import AlphaKernel

logger = logging.getLogger("astrbot_plugin_sylanne")


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
        """原子写入 kernel 快照到磁盘。写入前执行一致性自检。"""
        self._consistency_check(kernel)
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(kernel.session_key)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    kernel.snapshot(), ensure_ascii=False, sort_keys=True
                )
            )
            f.flush()
            os.fsync(f.fileno())
        try:
            os.replace(tmp, path)
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

    def _consistency_check(self, kernel: AlphaKernel) -> dict[str, Any]:
        """状态一致性自检守护：检查内部状态合法性并自动修正。

        检查项：
          1. 所有人格参数在 [0.0, 1.0] 范围内
          2. scar_algebra 的 modifier 缓存与实际伤痕列表一致
          3. void_calculus 的 pressure 不超过 5.0

        如果发现异常，logger.error 并尝试修正（clamp 到合法范围）。
        此方法应被定期调用（如 background_queue 空闲时）。

        Args:
            kernel: 要检查的 AlphaKernel 实例。

        Returns:
            包含检查结果的字典：corrections（修正数量）、details（修正详情列表）。
        """
        corrections: list[str] = []
        comp = kernel.computation

        # 1. 检查所有人格参数在 [0.0, 1.0] 范围内
        personality = comp._personality
        for trait, value in list(personality.items()):
            if not isinstance(value, (int, float)):
                continue
            if value < 0.0:
                logger.error(
                    f"Consistency check: personality trait '{trait}' = {value} < 0.0, "
                    f"clamping to 0.0"
                )
                personality[trait] = 0.0
                corrections.append(f"personality.{trait}: {value} -> 0.0")
            elif value > 1.0:
                logger.error(
                    f"Consistency check: personality trait '{trait}' = {value} > 1.0, "
                    f"clamping to 1.0"
                )
                personality[trait] = 1.0
                corrections.append(f"personality.{trait}: {value} -> 1.0")

        # 2. 检查 scar_algebra 的 modifier 缓存与实际伤痕列表一致
        scar_state = comp.engine.scar_state
        # 强制使缓存失效并重建，确保一致性
        old_cache_valid = scar_state._modifier_cache_valid
        if old_cache_valid:
            # 保存旧缓存值用于比较
            old_cache = dict(scar_state._modifier_cache)
            # 强制重建
            scar_state._modifier_cache_valid = False
            scar_state._ensure_modifier_cache()
            new_cache = dict(scar_state._modifier_cache)
            # 比较
            for dim in range(scar_state.n_dims):
                old_val = old_cache.get(dim, 1.0)
                new_val = new_cache.get(dim, 1.0)
                if abs(old_val - new_val) > 1e-6:
                    logger.error(
                        f"Consistency check: scar modifier cache mismatch at dim {dim}: "
                        f"cached={old_val:.6f}, actual={new_val:.6f}. Cache rebuilt."
                    )
                    corrections.append(
                        f"scar_modifier[{dim}]: {old_val:.6f} -> {new_val:.6f}"
                    )
        else:
            # 缓存本来就无效，重建即可
            scar_state._ensure_modifier_cache()

        # 3. 检查 void_calculus 的 pressure 不超过 5.0
        void_space = comp.engine.void_space
        for idx, void in enumerate(void_space.voids):
            if void.pressure > 5.0:
                logger.error(
                    f"Consistency check: void[{idx}].pressure = {void.pressure:.4f} > 5.0, "
                    f"clamping to 5.0"
                )
                corrections.append(
                    f"void[{idx}].pressure: {void.pressure:.4f} -> 5.0"
                )
                void.pressure = 5.0
            elif void.pressure < 0.0:
                logger.error(
                    f"Consistency check: void[{idx}].pressure = {void.pressure:.4f} < 0.0, "
                    f"clamping to 0.0"
                )
                corrections.append(
                    f"void[{idx}].pressure: {void.pressure:.4f} -> 0.0"
                )
                void.pressure = 0.0

        if corrections:
            logger.error(
                f"Consistency check completed with {len(corrections)} correction(s): "
                f"{corrections}"
            )
        return {"corrections": len(corrections), "details": corrections}


class HotUpgradeManager:
    """插件热升级管理器（接口定义，完整实现需要 AstrBot 框架支持）。"""

    def __init__(self):
        self._upgrade_in_progress: bool = False
        self._last_upgrade: float = 0

    def can_upgrade(self) -> bool:
        """检查是否可以安全升级。"""
        return not self._upgrade_in_progress

    def prepare_upgrade(self) -> dict:
        """准备升级：收集需要迁移的状态。"""
        self._upgrade_in_progress = True
        return {
            "status": "prepared",
            "note": "Full hot-upgrade requires AstrBot framework support. "
            "Current implementation saves state before reload.",
        }

    def complete_upgrade(self):
        """完成升级。"""
        import time

        self._upgrade_in_progress = False
        self._last_upgrade = time.time()

    def abort_upgrade(self):
        """中止升级。"""
        self._upgrade_in_progress = False
