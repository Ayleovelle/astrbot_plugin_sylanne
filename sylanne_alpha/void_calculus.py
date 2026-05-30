"""Sylanne-Embodiment 计算核心层：虚空微积分（Void Calculus）。

在 7 层计算栈中的位置：L3 VoidScar 层的"虚空"部分。
职责：将"缺席"（absence）作为一等计算原语。虚空不是从已有事物推导出来的——
它们是独立的对象，拥有自己的生命周期、压力动力学，以及与伤痕代数的耦合关系。

核心概念：
  - Void（虚空）：一个"不在场"的对象，由边界向量集合定义
  - VoidGhost（虚空残影）：死亡虚空的残留物，永久存在，影响未来的检测灵敏度
  - VoidSpace（虚空空间）：管理活跃虚空、残影，以及收缩/加深/创生/合并/分裂操作
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable


class SilenceTexture:
    """沉默质感分类——不同类型的沉默有不同的情感含义。

    四种质感：
      - WAITING: 期待回复（短沉默 + 中性/正向情绪）
      - DIGESTING: 需要时间处理（中等沉默 + 负向情绪）
      - DISTANT: 关系冷却（长沉默 + 低关系温度）
      - CONTENT: 满足无需言语（短沉默 + 正向情绪）
    """

    WAITING = "waiting"
    DIGESTING = "digesting"
    DISTANT = "distant"
    CONTENT = "content"

    @staticmethod
    def classify(
        silence_duration: float,
        last_valence: float,
        relationship_warmth: float,
    ) -> str:
        """根据沉默时长、最后情绪和关系温度分类沉默质感。

        Args:
            silence_duration: 沉默持续时间（秒）
            last_valence: 最后一次交互的情绪效价 [-1, 1]
            relationship_warmth: 关系温度 [0, 1]

        Returns:
            沉默质感字符串
        """
        # silence < 5min + valence > 0 → content
        if silence_duration < 300 and last_valence > 0:
            return SilenceTexture.CONTENT
        # silence < 30min + valence < -0.3 → digesting
        if silence_duration < 1800 and last_valence < -0.3:
            return SilenceTexture.DIGESTING
        # silence > 2h + warmth < 0.3 → distant
        if silence_duration > 7200 and relationship_warmth < 0.3:
            return SilenceTexture.DISTANT
        # 其他 → waiting
        return SilenceTexture.WAITING


@dataclass(slots=True)
class Void:
    """一等缺席对象——虚空。

    虚空由其"边界"（boundary）定义：一组 HDC 向量，代表"被回避的话题"。
    虚空有自己的生命周期：
      - 创生：检测到话题突然偏转时诞生
      - 成长：边界被触碰时收缩，被回避时加深
      - 压力积累：随年龄增长，未被触碰的虚空压力持续上升
      - 死亡：边界完全被收缩后死亡，留下 VoidGhost 残影

    与伤痕代数的耦合：当压力超过阈值时，通过 Γ 耦合触发伤痕创伤事件。
    """

    boundary: list[bytes]
    depth: float = 0.0
    pressure: float = 0.0
    age: int = 0
    beta: float = 0.0
    _estimated_boundary_size: int = 5
    _last_boundary_hash: int = 0

    @property
    def is_ghost(self) -> bool:
        return len(self.boundary) == 0 and self.depth > 0

    @property
    def is_alive(self) -> bool:
        return len(self.boundary) > 0

    @property
    def boundary_completeness(self) -> float:
        if self._estimated_boundary_size <= 0:
            return 1.0
        return len(self.boundary) / (len(self.boundary) + self._estimated_boundary_size)

    def tick(self, pressure_cap: float = 100.0):
        """虚空老化：每 tick 增加年龄并按公式积累压力。

        压力公式：pressure += depth * log(age + 1) * (1 - beta)
        其中 beta = 边界完整度。边界越不完整（被触碰越多），压力积累越快。
        这模拟了"越是回避的话题，内心压力越大"的心理动力学。
        """
        self.age += 1
        self.beta = self.boundary_completeness
        if self.depth > 0 and self.age > 0:
            self.pressure += self.depth * math.log(self.age + 1) * (1.0 - self.beta)
        self.pressure = min(self.pressure, pressure_cap)

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary_count": len(self.boundary),
            "boundary": [b.hex() for b in self.boundary],
            "depth": self.depth,
            "pressure": self.pressure,
            "age": self.age,
            "beta": self.beta,
            "is_ghost": self.is_ghost,
        }


@dataclass(slots=True)
class VoidGhost:
    """虚空残影——死亡虚空的永久残留物。

    不再产生压力，但会影响未来虚空的检测灵敏度（ghost_bonus）。
    模拟"曾经的创伤虽已愈合，但留下了更敏感的检测能力"。
    """

    depth: float
    age_at_death: int
    last_boundary_hash: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "depth": self.depth,
            "age_at_death": self.age_at_death,
        }


class VoidSpace:
    """虚空微积分引擎：管理活跃虚空、残影，以及所有虚空操作。

    核心操作（每 tick 按顺序执行）：
      1. tick: 所有虚空老化，压力积累
      2. contract: 事件向量触碰虚空边界 → 移除相似的边界点
      3. deepen: 检测到回避行为（话题突变 + 高惊讶）→ 加深附近虚空
      4. genesis: 检测到新虚空形成条件 → 创建新虚空
      5. reap: 清除边界为空的死亡虚空，留下残影
      6. merge: 合并边界重叠的虚空
      7. split: 分裂边界呈双峰分布的虚空

    与其他组件的关系：
      - 接收 L1 HDCEncoder 的输出作为事件向量
      - 接收 L2 PredictiveCodingGate 的惊讶度
      - 通过 Γ 耦合向 ScarredState 发送创伤事件
      - 通过 Φ 耦合接收 ScarredState 的麻木信息
    """

    __slots__ = (
        "voids",
        "ghosts",
        "similarity_fn",
        "_contract_threshold",
        "_split_threshold",
        "_merge_threshold",
        "_detection_threshold",
        "_pressure_threshold",
        "_max_voids",
        "_tick",
        "_creation_cooldown",
        "_cooldown_duration",
        "_pressure_cap",
    )

    def __init__(
        self,
        similarity_fn: Callable[[bytes, bytes], float],
        max_voids: int = 50,
        contract_threshold: float = 0.6,
        split_threshold: float = 0.3,
        merge_threshold: float = 0.7,
        detection_threshold: float = 0.4,
        pressure_threshold: float = 4.5,
    ):
        self.similarity_fn = similarity_fn
        self.voids: list[Void] = []
        self.ghosts: list[VoidGhost] = []
        self._contract_threshold = contract_threshold
        self._split_threshold = split_threshold
        self._merge_threshold = merge_threshold
        self._detection_threshold = detection_threshold
        self._pressure_threshold = pressure_threshold
        self._max_voids = max_voids
        self._tick = 0
        self._creation_cooldown = 0
        self._cooldown_duration = 3
        self._pressure_cap = 5.0

    def process(
        self, event_vec: bytes, surprise: float, prev_similarity: float
    ) -> dict[str, Any]:
        """主入口：处理一个事件通过虚空空间。

        按顺序执行：老化 → 收缩 → 加深 → 创生 → 收割 → 合并 → 分裂。

        Args:
            event_vec: HDC 编码的事件向量
            surprise: 来自预测编码门控的惊讶度
            prev_similarity: 当前事件与上一事件的相似度（用于检测话题偏转）

        Returns:
            包含各操作结果和耦合事件的诊断字典
        """
        self._tick += 1
        result: dict[str, Any] = {
            "voids_contracted": 0,
            "voids_deepened": 0,
            "voids_born": 0,
            "voids_died": 0,
            "total_pressure": 0.0,
            "coupling_events": [],
        }

        # Age all voids (pressure accumulates)
        for v in self.voids:
            v.tick(self._pressure_cap)

        for v in self.voids:
            v.pressure = min(v.pressure, self._pressure_cap)

        # Contract: event touches void boundaries
        result["voids_contracted"] = self._contract_all(event_vec)

        # Deepen: detect avoidance (sudden topic shift + high surprise)
        if (
            prev_similarity < (1.0 - self._detection_threshold)
            and surprise > self._detection_threshold
        ):
            result["voids_deepened"] = self._deepen_nearby(event_vec)

        # Genesis: detect new void formation
        if self._should_create_void(event_vec, surprise, prev_similarity):
            self._create_void(event_vec)
            result["voids_born"] = 1

        # Kill dead voids (empty boundary)
        result["voids_died"] = self._reap_dead()

        # Merge overlapping voids
        self._merge_pass()

        # Split voids with bimodal boundaries
        self._split_pass()

        # Compute coupling events (voids that exceed pressure threshold)
        for v in self.voids:
            if v.pressure > self._pressure_threshold:
                result["coupling_events"].append(
                    {
                        "pressure": v.pressure,
                        "depth": v.depth,
                        "boundary_size": len(v.boundary),
                        "dim_hint": len(v.boundary) % 8,
                    }
                )

        result["total_pressure"] = sum(v.pressure for v in self.voids)
        result["active_voids"] = len(self.voids)
        result["ghosts"] = len(self.ghosts)
        return result

    def _contract_all(self, event_vec: bytes) -> int:
        """收缩操作：移除与事件向量相似的边界点。

        当用户主动谈及某个"被回避的话题"时，该话题对应的虚空边界被侵蚀。
        边界被移除后，压力按比例衰减（话题被正面面对 → 压力释放）。
        """
        contracted = 0
        for v in self.voids:
            before = len(v.boundary)
            removed_vecs = [
                b
                for b in v.boundary
                if self.similarity_fn(event_vec, b) >= self._contract_threshold
            ]
            if removed_vecs:
                v._last_boundary_hash = hash(bytes(removed_vecs[-1]))
            v.boundary = [
                b
                for b in v.boundary
                if self.similarity_fn(event_vec, b) < self._contract_threshold
            ]
            if len(v.boundary) < before:
                contracted += 1
                removed = before - len(v.boundary)
                v.pressure *= 1.0 - removed / max(1, before)
        return contracted

    def _deepen_nearby(self, event_vec: bytes) -> int:
        """加深操作：当检测到回避行为时，加深附近虚空。

        "附近"定义为：虚空的某个边界点与事件向量的相似度超过 split_threshold。
        这模拟了"越是绕着话题走，虚空越深"的动力学。
        """
        deepened = 0
        for v in self.voids:
            for b in v.boundary:
                if self.similarity_fn(event_vec, b) > self._split_threshold:
                    v.depth += 0.1
                    deepened += 1
                    break
        return deepened

    def _should_create_void(
        self, event_vec: bytes, surprise: float, prev_sim: float
    ) -> bool:
        """虚空创生条件判断：检测话题的突然偏转。

        条件：高惊讶 + 与前一事件低相似度 = 话题突然转向（可能在回避什么）。
        残影加成：附近有深度 > 0.5 的残影时降低创生阈值（旧伤附近更敏感）。
        抗性：已有虚空越多，创生阈值越高（防止虚空爆炸）。
        """
        if self._creation_cooldown > 0:
            self._creation_cooldown -= 1
            return False
        if len(self.voids) >= self._max_voids:
            return False
        if surprise < self._detection_threshold:
            return False
        if prev_sim > (1.0 - self._detection_threshold):
            return False
        # Ghost sensitivity: lower threshold near previous voids
        ghost_bonus = sum(0.1 for g in self.ghosts if g.depth > 0.5)
        effective_threshold = max(0.1, self._detection_threshold - ghost_bonus)
        # Resistance increases with existing void count
        if len(self.voids) > 0:
            effective_threshold += len(self.voids) * 0.02
        return surprise > effective_threshold

    def _create_void(self, deflected_from: bytes):
        """创建新虚空：以"被偏转离开的话题"向量作为初始边界。"""
        v = Void(
            boundary=[deflected_from],
            depth=0.0,
            pressure=0.0,
            age=0,
            beta=0.0,
        )
        self.voids.append(v)
        self._creation_cooldown = self._cooldown_duration

    def set_cooldown(self, openness: float) -> None:
        """根据人格开放性设置创生冷却时间。开放性越高，冷却越长（不急于形成新虚空）。"""
        self._cooldown_duration = int(2 + openness * 3)

    def _reap_dead(self) -> int:
        """收割死亡虚空：边界为空的虚空死亡，深度 > 0 的留下残影。"""
        dead = [v for v in self.voids if not v.boundary]
        for v in dead:
            if v.depth > 0:
                ghost = VoidGhost(
                    depth=v.depth,
                    age_at_death=v.age,
                    last_boundary_hash=v._last_boundary_hash,
                )
                self.ghosts.append(ghost)
        self.voids = [v for v in self.voids if v.boundary]
        if len(self.ghosts) > 50:
            self.ghosts = self.ghosts[-50:]
        return len(dead)

    def _merge_pass(self):
        """合并操作：将边界重叠的虚空合并为一个（它们本质上是同一个"缺席"）。"""
        if len(self.voids) < 2:
            return
        merged_indices: set[int] = set()
        new_voids: list[Void] = []
        for i in range(len(self.voids)):
            if i in merged_indices:
                continue
            for j in range(i + 1, len(self.voids)):
                if j in merged_indices:
                    continue
                if self._boundaries_overlap(self.voids[i], self.voids[j]):
                    merged = self._merge_two(self.voids[i], self.voids[j])
                    new_voids.append(merged)
                    merged_indices.add(i)
                    merged_indices.add(j)
                    break
            else:
                new_voids.append(self.voids[i])
        self.voids = new_voids

    def _boundaries_overlap(self, v1: Void, v2: Void) -> bool:
        for b1 in v1.boundary:
            for b2 in v2.boundary:
                if self.similarity_fn(b1, b2) > self._merge_threshold:
                    return True
        return False

    def _merge_two(self, v1: Void, v2: Void) -> Void:
        return Void(
            boundary=list(set(v1.boundary + v2.boundary)),
            depth=max(v1.depth, v2.depth),
            pressure=min(v1.pressure + v2.pressure, 5.0),
            age=max(v1.age, v2.age),
            beta=0.0,
        )

    def _split_pass(self):
        """分裂操作：将边界呈双峰分布的虚空分裂为两个独立虚空。"""
        new_voids: list[Void] = []
        for v in self.voids:
            if len(v.boundary) < 4:
                new_voids.append(v)
                continue
            cluster_a, cluster_b = self._try_split(v)
            if cluster_a is not None:
                new_voids.append(
                    Void(
                        boundary=cluster_a,
                        depth=v.depth,
                        pressure=v.pressure / 2,
                        age=0,
                        beta=0.0,
                    )
                )
                new_voids.append(
                    Void(
                        boundary=cluster_b,
                        depth=v.depth,
                        pressure=v.pressure / 2,
                        age=0,
                        beta=0.0,
                    )
                )
            else:
                new_voids.append(v)
        self.voids = new_voids

    def _try_split(self, v: Void) -> tuple[list[bytes] | None, list[bytes] | None]:
        """简单 2-means 分裂尝试：以第一个边界点为 pivot 将边界分为近/远两组。

        只有当两组之间的平均相似度低于 split_threshold 时才执行分裂。
        """
        if len(v.boundary) < 4:
            return None, None
        pivot = v.boundary[0]
        near = [b for b in v.boundary if self.similarity_fn(b, pivot) > 0.5]
        far = [b for b in v.boundary if self.similarity_fn(b, pivot) <= 0.5]
        if not near or not far:
            return None, None
        avg_inter = sum(
            self.similarity_fn(n, f) for n in near[:3] for f in far[:3]
        ) / max(1, min(9, len(near) * len(far)))
        if avg_inter < self._split_threshold:
            return near, far
        return None, None

    def total_pressure(self) -> float:
        return sum(v.pressure for v in self.voids)

    def coupling_output(self) -> list[dict[str, float]]:
        """返回超过压力阈值的虚空列表——它们准备好通过 Γ 耦合创伤伤痕状态。"""
        return [
            {"pressure": v.pressure, "depth": v.depth, "dim_hint": len(v.boundary) % 8}
            for v in self.voids
            if v.pressure > self._pressure_threshold
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "voids": [v.to_dict() for v in self.voids],
            "ghosts": [g.to_dict() for g in self.ghosts],
            "tick": self._tick,
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        self._tick = int(data.get("tick", 0))
        self.voids = []
        for vd in data.get("voids", []):
            v = Void(
                boundary=[bytes.fromhex(b) for b in vd.get("boundary", [])],
                depth=float(vd.get("depth", 0.0)),
            )
            v.pressure = float(vd.get("pressure", 0.0))
            v.age = int(vd.get("age", 0))
            v.beta = float(vd.get("beta", 0.0))
            self.voids.append(v)
        self.ghosts = []
        for gd in data.get("ghosts", []):
            self.ghosts.append(
                VoidGhost(
                    depth=float(gd.get("depth", 0.0)),
                    age_at_death=int(gd.get("age_at_death", 0)),
                )
            )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "active_voids": len(self.voids),
            "ghosts": len(self.ghosts),
            "total_pressure": self.total_pressure(),
            "max_depth": max((v.depth for v in self.voids), default=0.0),
            "tick": self._tick,
        }

    def set_personality_params(
        self,
        contract_threshold: float,
        split_threshold: float,
        merge_threshold: float,
        pressure_cap: float,
    ):
        self._contract_threshold = contract_threshold
        self._split_threshold = split_threshold
        self._merge_threshold = merge_threshold
        self._pressure_cap = pressure_cap


# ---------------------------------------------------------------------------
# 沉默的语义类型与破冰策略（Item 146）
# ---------------------------------------------------------------------------

SILENCE_BREAKERS: dict[str, str] = {
    "waiting": "试探性短句，确认对方是否还在",
    "digesting": "给予空间，等对方准备好再说",
    "distant": "轻量问候，不施压",
    "content": "自然延续，不刻意打破",
}


def get_silence_breaker(texture: str) -> str:
    """根据沉默的语义类型返回对应的破冰策略描述。

    Args:
        texture: 沉默纹理类型（waiting / digesting / distant / content）。

    Returns:
        破冰策略描述文本，未知类型返回空字符串。
    """
    return SILENCE_BREAKERS.get(texture, "")
