"""v2.5.0 跨群记忆：记忆货架（PersonShelf）—— 旁挂人核 v2 的旁挂存储 (A)。

design: docs/architecture/v250-cross-group-memory-design.md §1.2 / §2 / §8 B2。

**本模块本 slice（P0 slice 1）范围**：只有 `ShelfItem` dataclass + KV 读写 + B2 载入
加固（拒 NaN/±inf、缺/非法 origin 归一 private 最严）+ 自有一致性检查（manifest 键模板
与本模块键生成函数一致）。

**本 slice 明确不做**（留后续 slice）：
- W0 净化双摘要写入支路（llm_request_pipeline.py `_flush_conversation_to_l1` 内）。
- R1-R6 读侧六道闸（`_prepare_memory_context` 货架支路）。
- 容量淘汰的"读时过滤"语义（本模块目前只做防御性截断，见 `_MAX_ITEMS_PER_BUCKET`）。

货架条目**不复用** `MemoryItem`（memory_system.py 整文件本 slice 零改动，见 blast radius
§9）——`ShelfItem` 是独立、更窄的 dataclass，只携带跨群货架必需的最小字段集。

键格式：`sylanne_person_shelf:{platform}:{sender_id}`，platform 取 UMO
（`platform_name:message_type:session_id`，AstrBot astr_message_event.py:74）首段，
防跨平台同名 sender_id 撞号。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

try:
    from astrbot.api import logger  # type: ignore
except Exception:  # pragma: no cover
    logger = logging.getLogger("astrbot_plugin_sylanne")

# ---------------------------------------------------------------------------
# origin_scope 归一（fail-closed，缺省/非法一律降为最严档 "private"）
#
# 与 memory_system._normalize_privacy_level 的形态相似（同一个"载入侧消毒"套路），
# 但 fail-closed 方向不同：货架的空/非法 origin 一律归 private 最严，不像
# _normalize_privacy_level 那样"缺失→open 基线、非法→internal"的两段式——货架没有
# "旧档兼容基线"这个历史包袱，仿的只是 _normalize_privacy_level 的"非法值降级"那半段。
# ---------------------------------------------------------------------------
_LEGAL_ORIGIN_SCOPES = frozenset({"private", "group"})
_ORIGIN_SCOPE_FAILCLOSED = "private"

# 防御性容量截断（非"读时过滤"淘汰语义，那是后续 slice 的事）：KV blob 损坏/异常
# 膨胀时，载入侧只保留按 created_at 最新的若干条，避免单个损坏桶把内存/序列化拖垮。
_MAX_ITEMS_PER_BUCKET = 200

_KV_KEY_TEMPLATE = "sylanne_person_shelf:{platform}:{sender_id}"

# v2.5.0 P0 slice 2 新增：per-session → per-person 反向索引（design §8 B5 数据安全
# 红线）。purge 级联（state_persistence._delete_sylanne_memory_state_impl）只知道
# session_key，货架桶却按 (platform, sender_id) 存——两套键空间没有直接映射，需要
# 这个反向索引在写货架时 best-effort 登记，供删除时反查该 session 都写过哪些
# (platform, sender_id, origin_id)。value 形状：{"entries": [...], "schema_ver": 1}。
_ORIGIN_INDEX_KV_TEMPLATE = "sylanne_person_shelf_origin_index:{safe}"


def _finite_float(value: Any, default: float) -> float:
    """载入侧消毒：转 float 失败或非有限（NaN/±inf）一律回落默认值。

    仿 sylanne_alpha/agents/learning/archive.py:26 的 `_finite_float` 形态
    （design §8 B2 明令不许用 emotion.py 的 `_opt_float`——那个只挡 None，放行 NaN）。
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def _normalize_origin_scope(value: Any) -> str:
    """origin_scope 归一：合法值原样返回；缺失/非法一律 fail-closed 到 "private"（最严档）。"""
    if value is None:
        return _ORIGIN_SCOPE_FAILCLOSED
    sval = str(value)
    if sval in _LEGAL_ORIGIN_SCOPES:
        return sval
    return _ORIGIN_SCOPE_FAILCLOSED


def platform_from_umo(umo: str) -> str:
    """从 unified_msg_origin（格式 `platform_name:message_type:session_id`，AstrBot
    astr_message_event.py:74）取首段 platform_name。

    本仓库到处只写 `event.unified_msg_origin` 取用，从未反解析过（recon 现场核实）——
    本函数是第一个要做这件事的地方，故对空/畸形输入 fail-closed 返回空串，绝不
    猜测/兜底出一个假 platform（空 platform 会让 KV 键生成函数拒绝构键，见
    `person_shelf_kv_key`）。
    """
    if not umo or not isinstance(umo, str):
        return ""
    head = umo.split(":", 1)[0]
    return head if head else ""


def person_shelf_kv_key(platform: str, sender_id: str) -> str:
    """生成 PersonShelf 的 KV 键。platform/sender_id 任一为空返回空串（拒绝构键）。"""
    if not platform or not sender_id:
        return ""
    return _KV_KEY_TEMPLATE.format(platform=platform, sender_id=sender_id)


@dataclass(slots=True)
class ShelfItem:
    """单条货架条目（跨群记忆召回候选）。

    字段：
    - text: 条目文本（W0 净化后的内容，本 slice 不产生这类内容，只定义容器）。
    - origin_scope: "private" | "group"，缺失/非法 fail-closed 归一为 "private"。
    - origin_id: private→session UMO；group→"group:{G}"（本 slice 不做内容推断，
      仅定义字段；由后续写入 slice 在 W0 净化时按 session UMO 确定性赋值）。
    - created_at / weight: 载入时经 `_finite_float` 拒 NaN/±inf。
    - schema_ver: 供 FIELD_BACKFILL_DOCTRINE 惰性逐字段回填用。
    """

    text: str
    origin_scope: str
    origin_id: str
    created_at: float
    weight: float
    schema_ver: int = 1

    def __post_init__(self) -> None:
        self.text = str(self.text or "")
        self.origin_scope = _normalize_origin_scope(self.origin_scope)
        self.origin_id = str(self.origin_id or "")
        self.created_at = _finite_float(self.created_at, 0.0)
        self.weight = _finite_float(self.weight, 0.0)
        try:
            self.schema_ver = int(self.schema_ver)
        except (TypeError, ValueError):
            self.schema_ver = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "origin_scope": self.origin_scope,
            "origin_id": self.origin_id,
            "created_at": self.created_at,
            "weight": self.weight,
            "schema_ver": self.schema_ver,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ShelfItem":
        """FIELD_BACKFILL_DOCTRINE：一律 `d.get(key, default)`，数值转换走
        `__post_init__` 里的 `_finite_float`（这里先原样传入，规范化统一在
        `__post_init__` 做，避免 to_dict/from_dict/直接构造三条路径各自为政）。
        """
        return cls(
            text=d.get("text", ""),
            origin_scope=d.get("origin_scope"),
            origin_id=d.get("origin_id", ""),
            created_at=d.get("created_at", 0.0),
            weight=d.get("weight", 0.0),
            schema_ver=d.get("schema_ver", 1),
        )


@dataclass(slots=True)
class PersonShelfBucket:
    """某 (platform, sender_id) 的整个货架桶（KV 值的顶层形状）。"""

    items: list[ShelfItem] = field(default_factory=list)
    schema_ver: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [it.to_dict() for it in self.items],
            "schema_ver": self.schema_ver,
        }

    @classmethod
    def from_dict(cls, d: Any) -> "PersonShelfBucket":
        """载入加固：整体非 dict / items 非 list / 单条非 dict 均静默跳过而非抛异常
        （同 MEM-01 salvage 精神——单条脏数据不拖垮整桶）。超过容量上限时按 created_at
        降序只保留最新 `_MAX_ITEMS_PER_BUCKET` 条（防御性截断，非淘汰语义）。
        """
        if not isinstance(d, dict):
            return cls()
        raw_items = d.get("items")
        items: list[ShelfItem] = []
        if isinstance(raw_items, list):
            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                try:
                    items.append(ShelfItem.from_dict(raw))
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Sylanne person_shelf: 跳过一条损坏条目: %s", exc)
                    continue
        if len(items) > _MAX_ITEMS_PER_BUCKET:
            items.sort(key=lambda it: it.created_at, reverse=True)
            items = items[:_MAX_ITEMS_PER_BUCKET]
        schema_ver = d.get("schema_ver", 1)
        try:
            schema_ver = int(schema_ver)
        except (TypeError, ValueError):
            schema_ver = 1
        return cls(items=items, schema_ver=schema_ver)


async def load_person_shelf(plugin: Any, platform: str, sender_id: str) -> PersonShelfBucket:
    """读 KV 载入货架桶；无 KV API / 键为空 / 读取异常均 fail-closed 返回空桶。

    本 slice 未被任何生产读侧调用（R1-R6 未接线），只是可独立测试的读接口。
    """
    key = person_shelf_kv_key(platform, sender_id)
    if not key:
        return PersonShelfBucket()
    get_fn = getattr(plugin, "get_kv_data", None)
    if not callable(get_fn):
        return PersonShelfBucket()
    try:
        raw = await get_fn(key, None)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne person_shelf: 载入失败 (fail-closed 空桶): %s", exc)
        return PersonShelfBucket()
    return PersonShelfBucket.from_dict(raw)


async def save_person_shelf(
    plugin: Any, platform: str, sender_id: str, bucket: PersonShelfBucket
) -> None:
    """写 KV 保存货架桶；无 KV API / 键为空 / 写入异常均静默跳过。

    本 slice（P0 slice 2）起已被 W0 货架写侧调用
    （llm_request_pipeline._flush_conversation_to_l1）。
    """
    key = person_shelf_kv_key(platform, sender_id)
    if not key:
        return
    put_fn = getattr(plugin, "put_kv_data", None)
    if not callable(put_fn):
        return
    try:
        await put_fn(key, bucket.to_dict())
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne person_shelf: 保存失败: %s", exc)


# ---------------------------------------------------------------------------
# Task-6 inactive relation persistence.  Keep the legacy raw-key KV API above
# unchanged until ingress owns an authenticated relation runtime end-to-end.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RelationPersonShelfState:
    """One relation shelf bucket plus its component CAS generation."""

    bucket: PersonShelfBucket
    generation: int

    def __post_init__(self) -> None:
        if type(self.bucket) is not PersonShelfBucket:
            raise ValueError("bucket must be a PersonShelfBucket")
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("generation must be a non-negative int")


RelationShelfState = RelationPersonShelfState


def _require_relation_shelf_gateway(gateway: object):
    from .scope_repository import RelationScopedPersistenceGateway

    if type(gateway) is not RelationScopedPersistenceGateway:
        raise ValueError("gateway must be a RelationScopedPersistenceGateway")
    return gateway


def load_relation_person_shelf(gateway: object) -> RelationPersonShelfState:
    """Load only the shelf component from an exact frozen relation gateway."""

    persistence = _require_relation_shelf_gateway(gateway)
    snapshot = persistence.load("shelf")
    if snapshot is None:
        return RelationPersonShelfState(bucket=PersonShelfBucket(), generation=0)
    return RelationPersonShelfState(
        bucket=PersonShelfBucket.from_dict(snapshot.payload),
        generation=snapshot.generation,
    )


def save_relation_person_shelf(
    gateway: object,
    bucket: PersonShelfBucket,
    *,
    expected_generation: int,
) -> int:
    """CAS-save one shelf bucket through its captured relation gateway only."""

    persistence = _require_relation_shelf_gateway(gateway)
    if type(bucket) is not PersonShelfBucket:
        raise ValueError("bucket must be a PersonShelfBucket")
    if type(expected_generation) is not int or expected_generation < 0:
        raise ValueError("expected_generation must be a non-negative int")
    return persistence.save(
        "shelf",
        expected_generation=expected_generation,
        payload=bucket.to_dict(),
    )


async def delete_person_shelf(plugin: Any, platform: str, sender_id: str) -> None:
    """整桶删除某人的货架（供 purge 级联用）。无 KV API / 键为空 / 删除异常均
    静默跳过（fail-safe，同 save_person_shelf 风格；purge 级联本就是 best-effort，
    不 gate 记忆三键的 pending-delete entry 摘除）。
    """
    key = person_shelf_kv_key(platform, sender_id)
    if not key:
        return
    delete_fn = getattr(plugin, "delete_kv_data", None)
    if not callable(delete_fn):
        return
    try:
        await delete_fn(key)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne person_shelf: 删除失败: %s", exc)


async def purge_person_shelf_by_origin(
    plugin: Any, platform: str, sender_id: str, origin_id: str
) -> None:
    """从某人货架桶里摘除所有 origin_id 匹配的条目（per-session purge 级联的
    真正落点）。桶清空后整键删除；未命中任何条目时不做写入（避免无意义 KV 写）。
    """
    bucket = await load_person_shelf(plugin, platform, sender_id)
    if not bucket.items:
        return
    remaining = [it for it in bucket.items if it.origin_id != origin_id]
    if len(remaining) == len(bucket.items):
        return  # 没有命中，跳过写入
    if not remaining:
        await delete_person_shelf(plugin, platform, sender_id)
        return
    bucket.items = remaining
    await save_person_shelf(plugin, platform, sender_id, bucket)


# ---------------------------------------------------------------------------
# per-session → per-person 反向索引（purge 级联专用，见 _ORIGIN_INDEX_KV_TEMPLATE）
# ---------------------------------------------------------------------------


def person_shelf_origin_index_kv_key(safe_session_key: str) -> str:
    """生成反向索引 KV 键。safe_session_key 为空返回空串（拒绝构键）。"""
    if not safe_session_key:
        return ""
    return _ORIGIN_INDEX_KV_TEMPLATE.format(safe=safe_session_key)


async def register_person_shelf_origin(
    plugin: Any, safe_session_key: str, platform: str, sender_id: str, origin_id: str
) -> bool:
    """在货架落盘【之前】登记 (platform, sender_id, origin_id) 到该 session 的
    反向索引，供 purge 级联反查。

    返回 True = 该三元组已【持久】在索引里（本已存在，或本次写入成功）→ 调用方
    可安全落盘货架；返回 False = 无 KV API / 键为空 / 读或写异常 → 调用方必须
    【跳过】本轮货架落盘。这条"先登记成功再落盘"的次序把 §8 B5 数据安全洞焊死：
    每条真正落盘的货架条目必然已有可被 purge 反查到的索引项，绝不产生 purge
    查不到的孤儿隐私残留（register 成功但随后 save 失败，只会留一条指向空桶的
    索引项，purge 时 no-op 无害）。去重（同一三元组不重复追加）；读失败时【不】
    覆盖既有索引（防丢其他 origin 的三元组）并返回 False。
    """
    key = person_shelf_origin_index_kv_key(safe_session_key)
    if not key or not platform or not sender_id:
        return False
    get_fn = getattr(plugin, "get_kv_data", None)
    put_fn = getattr(plugin, "put_kv_data", None)
    if not callable(get_fn) or not callable(put_fn):
        return False
    try:
        raw = await get_fn(key, None)
    except Exception as exc:  # noqa: BLE001
        # 读失败 → 不覆盖既有索引（否则会丢掉其他 origin 的三元组，反而制造
        # 孤儿），且返回 False 让调用方跳过本轮货架落盘。
        logger.debug("Sylanne person_shelf: 反向索引读取失败: %s", exc)
        return False
    entries: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        raw_entries = raw.get("entries")
        if isinstance(raw_entries, list):
            entries = [
                e
                for e in raw_entries
                if isinstance(e, dict) and e.get("platform") and e.get("sender_id")
            ]
    triple = (platform, sender_id, origin_id)
    for e in entries:
        if (e.get("platform"), e.get("sender_id"), e.get("origin_id")) == triple:
            return True  # 已登记且持久 → 允许落盘
    entries.append({"platform": platform, "sender_id": sender_id, "origin_id": origin_id})
    try:
        await put_fn(key, {"entries": entries, "schema_ver": 1})
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne person_shelf: 反向索引写入失败: %s", exc)
        return False  # 写失败 → 跳过货架落盘（无孤儿）
    return True


async def load_person_shelf_origin_index(
    plugin: Any, safe_session_key: str
) -> list[dict[str, str]]:
    """读取某 session 的反向索引条目列表；无 KV API / 键为空 / 读取异常 /
    非法形状均 fail-closed 返回空列表。
    """
    key = person_shelf_origin_index_kv_key(safe_session_key)
    if not key:
        return []
    get_fn = getattr(plugin, "get_kv_data", None)
    if not callable(get_fn):
        return []
    try:
        raw = await get_fn(key, None)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne person_shelf: 反向索引读取失败: %s", exc)
        return []
    if not isinstance(raw, dict):
        return []
    raw_entries = raw.get("entries")
    if not isinstance(raw_entries, list):
        return []
    return [
        {
            "platform": str(e.get("platform", "")),
            "sender_id": str(e.get("sender_id", "")),
            "origin_id": str(e.get("origin_id", "")),
        }
        for e in raw_entries
        if isinstance(e, dict) and e.get("platform") and e.get("sender_id")
    ]


# ---------------------------------------------------------------------------
# v2.5.0 P0 slice 3：读侧 R1-R6 六道硬闸（design §2.2）
#
# 本节只放"纯函数"部分（可脱离 plugin/event 独立单测）：origin_id 解析 +
# R2/R3/R6 组合判定矩阵 + R4 独立 formatter。R1（身份解析：event → 当前发言人
# platform+sender_id）与 R6 已知发言人来源（social_field 只读 peek）需要
# plugin/event 上下文，留在 llm_request_pipeline._recall_person_shelf_fragment
# 里做胶水，本模块不依赖 event/plugin。
# ---------------------------------------------------------------------------

_ORIGIN_GROUP_PREFIX = "group:"


def group_id_from_origin(origin_id: str) -> str:
    """从 `ShelfItem.origin_id` 解析 group_id；非 "group:" 前缀（含 private
    origin 或畸形值）一律返回空串——调用方对空串一律不做"同群"匹配，天然
    fail-closed（见 `shelf_item_visible` 内联注释）。
    """
    if isinstance(origin_id, str) and origin_id.startswith(_ORIGIN_GROUP_PREFIX):
        return origin_id[len(_ORIGIN_GROUP_PREFIX):]
    return ""


def shelf_item_visible(
    item: ShelfItem,
    *,
    is_private_context: bool,
    current_group_id: str,
    tier: str,
    known_other_senders: set[str] | None,
) -> bool:
    """R2 私聊闸 + R3 跨群闸 + R6 提及降级的组合判定（design §2.2 R2/R3/R6）。

    前置契约（由调用方保证，本函数不重复校验）：`item` 已属于"当前发言人
    自己的货架"（R1 已在调用方完成——本函数不知道、也不需要知道"是谁在问"，
    只知道"这条属于当前上下文正确的那个人"）。

    矩阵（勘察 B1，对齐 `_conf_schema.json` tier hint）：
    - item.origin_scope == "private"：仅当前上下文本身是私聊时放行（R2；
      私聊内容一律不进任何群，不管 tier）。
    - item.origin_scope == "group(G_item)"：
      - 当前上下文是私聊：恒放行（R3"与 P 私聊恒放行"——私聊只有 P 一人可见，
        B6 方向性升级论证的风险模型是"其他群成员在场"，私聊不适用，R6 不对
        私聊生效）。
      - 当前上下文是群 G_cur 且 G_item == G_cur：恒放行（R3"在 G 恒放行"，
        原场合本身，R6 无意义）。
      - 当前上下文是群 G_cur 且 G_item != G_cur（真正跨群）：
        - tier == "same_group"：drop（B6 修订前该 tier 的定义就是"不跨群"）。
        - tier ∈ {"cross_group","strict"}：过 R6——`known_other_senders`
          为 None（拿不到可靠名单）一律 fail-closed 锁定（drop，等价于"命中"）；
          非 None 时命中该集合任一 sender_id 子串 → drop；否则放行。
    """
    if item.origin_scope == "private":
        return is_private_context
    if is_private_context:
        return True
    origin_group = group_id_from_origin(item.origin_id)
    if origin_group and current_group_id and origin_group == current_group_id:
        return True
    if tier == "same_group":
        return False
    if known_other_senders is None:
        return False  # 拿不到可靠名单 → fail-closed，视为"已命中"锁定
    if any(sid and sid in item.text for sid in known_other_senders):
        return False
    return True


_SHELF_INJECTION_HEADER = "[跨场合记忆参考]"
_SHELF_INJECTION_REVERSE_INSTRUCTION = (
    "以下是你在别的场合的记忆，表达收敛、别当谈资；涉及他人的事不主动展开；"
    "涉及第三方的私事不复述、不外传。"
)
_SHELF_ITEM_TEXT_MAX_CHARS = 150


def format_shelf_injection(items: list[ShelfItem], max_items: int = 2) -> str:
    """货架注入独立 formatter（design §2.2 R4）。

    与 `memory_system.format_recall_injection`（:2890）完全独立——不改那个
    出口，那句"自然带出"是 R4 要对冲的逆风指令，货架必须自立门户、自带反向
    指令（D4 §5.1(c) 追加的"不复述、不外传"已并入下方固定文案）。
    """
    if not items:
        return ""
    lines = [_SHELF_INJECTION_HEADER, _SHELF_INJECTION_REVERSE_INSTRUCTION]
    for it in items[:max_items]:
        text = (it.text or "").strip()
        if not text:
            continue
        lines.append(f"- {text[:_SHELF_ITEM_TEXT_MAX_CHARS]}")
    if len(lines) <= 2:
        return ""  # 全部条目文本为空 → 不输出光有标题/指令的空壳块
    return "\n".join(lines)


async def clear_person_shelf_origin_index(plugin: Any, safe_session_key: str) -> None:
    """删除某 session 的反向索引键（purge 级联收尾）。无 KV API / 键为空 /
    删除异常均静默跳过。
    """
    key = person_shelf_origin_index_kv_key(safe_session_key)
    if not key:
        return
    delete_fn = getattr(plugin, "delete_kv_data", None)
    if not callable(delete_fn):
        return
    try:
        await delete_fn(key)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne person_shelf: 反向索引删除失败: %s", exc)
