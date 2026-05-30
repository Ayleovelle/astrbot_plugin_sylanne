"""基础设施模块——合并 utils / bounded_dict / workset 的共享工具集。

包含：
- safe_ensure_future: 安全的异步任务调度
- BoundedDict: 带 LRU 驱逐和可选 TTL 过期的有界字典
- build_fragment_workset: 工作集构建（黑板/碎片模式）
- resolve_data_root: 数据目录解析（含旧路径自动迁移）
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

try:
    from astrbot.api import logger  # type: ignore
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path  # type: ignore
except ImportError:
    logger = logging.getLogger("astrbot_plugin_sylanne")  # type: ignore

    def get_astrbot_data_path() -> Path:  # type: ignore
        return Path.home()


_PLUGIN_NAME = "astrbot_plugin_sylanne"
_LEGACY_SUBDIR = "sylanne_alpha"


def resolve_data_root(config: dict[str, Any] | None = None) -> str:
    """解析 Sylanne 数据存储根目录，遵循 AstrBot plugin_data 规范。

    优先级：
      1. config["sylanne_alpha_root"]（用户显式指定）
      2. data/plugin_data/astrbot_plugin_sylanne/（规范路径）
      3. 若规范路径不存在但旧路径 data/sylanne_alpha/ 存在，自动迁移

    Returns:
        数据根目录的字符串路径。
    """
    cfg = config or {}
    explicit = cfg.get("sylanne_alpha_root")
    if explicit:
        return str(explicit)

    base = Path(get_astrbot_data_path())
    new_root = base / "plugin_data" / _PLUGIN_NAME
    legacy_root = base / _LEGACY_SUBDIR

    if new_root.exists():
        return str(new_root)

    if legacy_root.exists():
        try:
            new_root.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy_root), str(new_root))
            logger.info(f"Sylanne: migrated data {legacy_root} → {new_root}")
        except Exception as e:
            logger.warning(f"Sylanne: data migration failed ({e}), using legacy path")
            return str(legacy_root)

    new_root.mkdir(parents=True, exist_ok=True)
    return str(new_root)


# ---------------------------------------------------------------------------
# utils: 异步辅助工具
# ---------------------------------------------------------------------------


def safe_ensure_future(
    coro: Any, name: str = "task", task_list: list | None = None
) -> "asyncio.Task[Any]":
    """将协程安全地调度为 asyncio Task，并附加异常日志回调。

    Args:
        coro: 待调度的协程对象。
        name: 任务名称，用于异常日志标识。
        task_list: 可选的任务列表，任务创建时加入、完成时自动移除，
                   便于外部统一管理/取消后台任务。

    Returns:
        创建的 asyncio.Task 实例。
    """
    loop = asyncio.get_running_loop()
    task = loop.create_task(coro)
    if task_list is not None:
        task_list.append(task)

    def _done(t: "asyncio.Task[Any]") -> None:
        # 任务完成后从列表中移除，保持列表只含活跃任务
        if task_list is not None:
            try:
                task_list.remove(t)
            except ValueError:
                pass
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logger.warning(f"Sylanne background task [{name}] failed: {exc}")

    task.add_done_callback(_done)
    return task


# ---------------------------------------------------------------------------
# bounded_dict: 带 LRU 驱逐和可选 TTL 过期的有界字典
# ---------------------------------------------------------------------------


class BoundedDict(OrderedDict):
    """带最大容量（LRU 驱逐）和可选 TTL 过期的有序字典。

    继承自 OrderedDict，利用其 move_to_end 实现 O(1) 的 LRU 访问更新。
    驱逐时可触发 on_evict 回调，用于持久化被驱逐的对象（如将 host 状态写盘）。
    """

    def __init__(self, maxsize: int = 200, ttl: float = 0, on_evict=None):
        """初始化有界字典。

        Args:
            maxsize: 最大容量，超出时驱逐最旧条目。
            ttl: 条目存活时间（秒），0 表示不启用 TTL。
            on_evict: 驱逐回调 fn(key, value)，在条目被 LRU 驱逐时调用。
        """
        super().__init__()
        self.maxsize = maxsize
        self.ttl = ttl
        self._ts: dict[Any, float] = {}  # 记录每个 key 的写入时间戳（仅 TTL 模式）
        self._on_evict = on_evict

    def __setitem__(self, key: Any, value: Any) -> None:
        # 已存在的 key 更新时移到末尾，保持 LRU 语义
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if self.ttl:
            self._ts[key] = time.time()
        # 超容量时循环驱逐最旧条目（队首）
        while len(self) > self.maxsize:
            oldest = next(iter(self))
            self._ts.pop(oldest, None)
            value_evicted = super().__getitem__(oldest)
            del self[oldest]
            if self._on_evict:
                try:
                    self._on_evict(oldest, value_evicted)
                except Exception as exc:
                    logger.warning(
                        "BoundedDict on_evict callback failed for key %r: %s",
                        oldest,
                        exc,
                    )

    def __getitem__(self, key: Any) -> Any:
        # TTL 检查：过期则惰性删除并抛出 KeyError
        if self.ttl and key in self._ts:
            if time.time() - self._ts[key] > self.ttl:
                self._ts.pop(key, None)
                del self[key]
                raise KeyError(key)
        # 访问时移到末尾，更新 LRU 顺序
        if key in self:
            self.move_to_end(key)
        return super().__getitem__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        """获取值，不存在或已过期时返回 default。"""
        try:
            return self[key]
        except KeyError:
            return default

    def setdefault(self, key: Any, default: Any = None) -> Any:
        """若 key 不存在则设置为 default 并返回。"""
        if key not in self:
            self[key] = default
        return self[key]


# ---------------------------------------------------------------------------
# workset: 工作集构建
# ---------------------------------------------------------------------------

WORKSET_SCHEMA_VERSION = "sylanne.alpha.workset.v1"


def build_fragment_workset(
    *,
    session_key: str,
    fragments: list[str] | None = None,
    shadow: dict[str, Any] | None = None,
    memory_matches: list[dict[str, Any]] | None = None,
    max_items: int = 5,
    dialogue: dict[str, Any] | None = None,
    personality: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    assessor: dict[str, Any] | None = None,
    guard: dict[str, Any] | None = None,
    attention: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建工作集：聚合各子系统证据为统一的 prompt 注入数据结构。

    Args:
        session_key: 会话标识。
        fragments: 当前意图文本碎片列表。
        shadow: 影子连续性数据（上一轮未消费的延续信息）。
        memory_matches: 记忆检索匹配结果列表。
        max_items: 工作集最大条目数。
        dialogue: 对话子系统证据。
        personality: 人格子系统证据。
        body: 身体状态子系统证据。
        assessor: 评估器子系统证据。
        guard: 安全守卫子系统证据。
        attention: 注意力子系统证据。

    Returns:
        工作集字典，包含 items/evidence/coordination/prompt_fragment 等字段。
    """
    # 清洗碎片：去除空白、合并多余空格
    clean_fragments = [
        " ".join(str(fragment).split())
        for fragment in fragments or []
        if str(fragment).strip()
    ]
    current_intent = " ".join(clean_fragments).strip()
    shadow = dict(shadow or {})
    items: list[dict[str, Any]] = []

    # 当前意图权重最高
    if current_intent:
        items.append(
            {"kind": "current_intent", "text": current_intent[:500], "weight": 1.0}
        )
    # 影子连续性：上一轮的延续摘要，权重略低
    if shadow.get("summary"):
        items.append(
            {
                "kind": "shadow_continuity",
                "text": str(shadow["summary"])[:500],
                "weight": 0.85,
            }
        )
    # 记忆匹配：按权重降序排列加入
    for match in sorted(
        memory_matches or [],
        key=lambda item: float(item.get("weight") or 0.0),
        reverse=True,
    ):
        text = str(match.get("text") or "").strip()
        if text:
            items.append(
                {
                    "kind": "memory_match",
                    "id": str(match.get("id") or ""),
                    "text": text[:500],
                    "weight": float(match.get("weight") or 0.0),
                }
            )
    # 去重并截断到 max_items
    items = _dedupe(items)[: max(1, int(max_items))]

    # 影子消费策略：consume_once 表示本轮使用后不再保留
    consume_shadow = bool(shadow.get("consume") and shadow.get("summary"))

    # 收集各部门证据，构建黑板
    evidence = _evidence(
        dialogue=dialogue,
        memory_matches=items,
        personality=personality,
        body=body,
        assessor=assessor,
        guard=guard,
        attention=attention,
    )
    # 协调：决定主导部门和 fast/slow 路径分组
    coordination = _coordination(evidence, attention=attention, guard=guard)

    return {
        "schema_version": WORKSET_SCHEMA_VERSION,
        "session_key": session_key,
        "mode": "blackboard" if evidence else "fragment",
        "current_intent": current_intent,
        "items": items,
        "evidence": evidence,
        "coordination": coordination,
        "shadow": {
            "available": bool(shadow.get("summary")),
            "consumed": consume_shadow,
            "policy": "consume_once" if consume_shadow else "preserve",
        },
        # 根据模式选择渲染方式
        "prompt_fragment": _render_blackboard(evidence, coordination)
        if evidence
        else _render(items),
    }


def _evidence(
    *,
    dialogue: dict[str, Any] | None,
    memory_matches: list[dict[str, Any]],
    personality: dict[str, Any] | None,
    body: dict[str, Any] | None,
    assessor: dict[str, Any] | None,
    guard: dict[str, Any] | None,
    attention: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """收集各部门的证据，标注 fast/slow 路径。

    fast 路径：对话、记忆、身体、守卫、注意力（低延迟，可立即获得）
    slow 路径：人格、评估器（需要 LLM 推理，可能有延迟）
    """
    evidence: list[dict[str, Any]] = []
    for department, payload, path in (
        ("dialogue", dialogue, "fast"),
        (
            "memory",
            {"matches": memory_matches, "count": len(memory_matches)}
            if memory_matches
            else None,
            "fast",
        ),
        ("personality", personality, "slow"),
        ("body", body, "fast"),
        ("assessor", assessor, "slow"),
        ("guard", guard, "fast"),
        ("attention", attention, "fast"),
    ):
        if payload:
            evidence.append(
                {
                    "department": department,
                    "path": path,
                    "summary": _truncate_payload_values(payload),
                }
            )
    return evidence


def _coordination(
    evidence: list[dict[str, Any]],
    *,
    attention: dict[str, Any] | None,
    guard: dict[str, Any] | None,
) -> dict[str, Any]:
    """决定协调策略：主导部门、fast/slow 路径分组。

    优先级：attention 指定 > guard 存在 > 第一个部门 > none。
    核心策略：fast_path_never_waits_for_slow_path（实时性优先）。
    """
    departments = [item["department"] for item in evidence]
    primary = str((attention or {}).get("primary") or "")
    if primary not in departments:
        # guard 存在时优先（安全优先），否则取第一个部门
        primary = (
            "guard"
            if guard and "guard" in departments
            else (departments[0] if departments else "none")
        )
    return {
        "primary_department": primary,
        "fast_path": [
            item["department"] for item in evidence if item["path"] == "fast"
        ],
        "slow_path": [
            item["department"] for item in evidence if item["path"] == "slow"
        ],
        "policy": "fast_path_never_waits_for_slow_path",
    }


def _truncate_payload_values(payload: dict[str, Any]) -> dict[str, Any]:
    """递归截断 payload 中的长文本值，防止工作集过大。

    - 字符串截断到 300 字符
    - 列表截断到前 5 项
    - 跳过敏感/大体积字段（raw/prompt/request/response）
    """
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"raw", "raw_text", "raw_dialogue", "prompt", "request", "response"}:
            continue
        if isinstance(value, str):
            clean[key] = value[:300]
        elif isinstance(value, dict):
            clean[key] = _truncate_payload_values(value)
        elif isinstance(value, list):
            clean[key] = [
                _truncate_payload_values(item) if isinstance(item, dict) else item
                for item in value[:5]
            ]
        else:
            clean[key] = value
    return clean


def _render_blackboard(
    evidence: list[dict[str, Any]], coordination: dict[str, Any]
) -> str:
    """将黑板模式的证据渲染为 prompt 文本片段。"""
    if not evidence:
        return "Sylanne blackboard: empty."
    lines = [f"Sylanne blackboard: primary={coordination['primary_department']}"]
    for item in evidence:
        lines.append(f"- {item['department']}[{item['path']}]")
    return "\n".join(lines)


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 kind+text 去重，保留首次出现的条目。"""
    seen: set[str] = set()
    deduped = []
    for item in items:
        key = f"{item['kind']}\0{item.get('text', '')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _render(items: list[dict[str, Any]]) -> str:
    """将碎片模式的条目渲染为 prompt 文本片段。"""
    if not items:
        return "Sylanne workset: empty."
    lines = ["Sylanne workset:"]
    for item in items:
        lines.append(f"- {item['kind']}: {item['text']}")
    return "\n".join(lines)


__all__ = [
    "safe_ensure_future",
    "BoundedDict",
    "resolve_data_root",
    "WORKSET_SCHEMA_VERSION",
    "build_fragment_workset",
]
