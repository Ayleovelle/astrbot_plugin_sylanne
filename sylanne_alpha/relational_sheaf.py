"""关系层析（Relational Sheaf Theory）— 计算模块。

在单纯复形上实现胞腔层（cellular sheaves），用于建模多关系动力学。
将 Scar Algebra 从单一二元关系扩展到 N 个并发关系：
  - 通过层拉普拉斯扩散实现跨关系影响传播
  - 通过层上同调（H^1）度量关系一致性
  - 人格驱动的表示矩阵（presentation matrices）
  - 能量有界传播（公理 S5）

数学基础：
- 层（Sheaf）：在拓扑空间上的"局部→全局"数据结构
- 上同调 H^1：度量"局部一致但全局矛盾"的维度数
- 拉普拉斯算子：驱动信息在关系网络中的扩散

参考: theory/relational_sheaf/axioms.md
"""

from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# 关系类型枚举（轻量级，无需额外导入）
# ---------------------------------------------------------------------------

INTIMATE = 0  # 亲密关系
FRIENDLY = 1  # 友好关系
FORMAL = 2  # 正式关系
ADVERSARIAL = 3  # 对抗关系

_REL_TYPE_NAMES = ("intimate", "friendly", "formal", "adversarial")


def _rel_type_from_str(s: str) -> int:
    """将字符串关系类型转为整数枚举。无法识别时默认为 FRIENDLY。"""
    s_lower = s.lower()
    for i, name in enumerate(_REL_TYPE_NAMES):
        if s_lower == name:
            return i
    return FRIENDLY  # default


# ---------------------------------------------------------------------------
# 线性代数辅助函数（纯 Python 实现，无 numpy 依赖）
# 用于小规模矩阵运算（≤10x10），性能足够（<0.1ms）
# ---------------------------------------------------------------------------


def _mat_zeros(rows: int, cols: int) -> list[list[float]]:
    return [[0.0] * cols for _ in range(rows)]


def _mat_identity(n: int) -> list[list[float]]:
    m = _mat_zeros(n, n)
    for i in range(n):
        m[i][i] = 1.0
    return m


def _mat_mul(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    """矩阵乘法 A (m x k) @ B (k x n) -> (m x n)。"""
    m = len(A)
    k = len(A[0]) if m > 0 else 0
    n = len(B[0]) if len(B) > 0 else 0
    C = _mat_zeros(m, n)
    for i in range(m):
        for j in range(n):
            s = 0.0
            for p in range(k):
                s += A[i][p] * B[p][j]
            C[i][j] = s
    return C


def _mat_transpose(A: list[list[float]]) -> list[list[float]]:
    if not A:
        return []
    rows, cols = len(A), len(A[0])
    T = _mat_zeros(cols, rows)
    for i in range(rows):
        for j in range(cols):
            T[j][i] = A[i][j]
    return T


def _mat_vec(A: list[list[float]], v: list[float]) -> list[float]:
    """矩阵-向量乘积 A @ v。"""
    return [sum(A[i][j] * v[j] for j in range(len(v))) for i in range(len(A))]


def _vec_sub(a: list[float], b: list[float]) -> list[float]:
    return [a[i] - b[i] for i in range(len(a))]


def _vec_add(a: list[float], b: list[float]) -> list[float]:
    return [a[i] + b[i] for i in range(len(a))]


def _vec_scale(v: list[float], s: float) -> list[float]:
    return [x * s for x in v]


def _vec_norm_sq(v: list[float]) -> float:
    return sum(x * x for x in v)


def _vec_norm(v: list[float]) -> float:
    return math.sqrt(_vec_norm_sq(v))


def _mat_frobenius(A: list[list[float]]) -> float:
    return math.sqrt(sum(A[i][j] ** 2 for i in range(len(A)) for j in range(len(A[0]))))


def _mat_add(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    rows, cols = len(A), len(A[0])
    return [[A[i][j] + B[i][j] for j in range(cols)] for i in range(rows)]


def _mat_scale(A: list[list[float]], s: float) -> list[list[float]]:
    return [[A[i][j] * s for j in range(len(A[0]))] for i in range(len(A))]


def _eigenvalues_symmetric(M: list[list[float]], max_iter: int = 50) -> list[float]:
    """用 Jacobi 迭代法近似计算小型对称矩阵的特征值。

    适用于 ≤10x10 的矩阵（<0.1ms）。
    返回升序排列的特征值列表。
    """
    n = len(M)
    if n == 0:
        return []
    if n == 1:
        return [M[0][0]]

    # Copy M
    A = [list(row) for row in M]

    for _ in range(max_iter * n):
        # Find largest off-diagonal element
        p, q, max_val = 0, 1, 0.0
        for i in range(n):
            for j in range(i + 1, n):
                if abs(A[i][j]) > max_val:
                    max_val = abs(A[i][j])
                    p, q = i, j
        if max_val < 1e-12:
            break

        # Compute rotation angle
        if abs(A[p][p] - A[q][q]) < 1e-15:
            theta = math.pi / 4.0
        else:
            theta = 0.5 * math.atan2(2.0 * A[p][q], A[p][p] - A[q][q])

        c, s = math.cos(theta), math.sin(theta)

        # Apply Givens rotation
        for i in range(n):
            if i == p or i == q:
                continue
            aip = A[i][p]
            aiq = A[i][q]
            A[i][p] = c * aip + s * aiq
            A[p][i] = A[i][p]
            A[i][q] = -s * aip + c * aiq
            A[q][i] = A[i][q]

        app = A[p][p]
        aqq = A[q][q]
        apq = A[p][q]
        A[p][p] = c * c * app + 2 * s * c * apq + s * s * aqq
        A[q][q] = s * s * app - 2 * s * c * apq + c * c * aqq
        A[p][q] = 0.0
        A[q][p] = 0.0

    eigenvalues = sorted(A[i][i] for i in range(n))
    return eigenvalues


def _kernel_dim(M: list[list[float]], tol: float = 1e-8) -> int:
    """通过行阶梯形式估计矩阵核空间的维度（cols - rank）。"""
    if not M or not M[0]:
        return 0
    rows, cols = len(M), len(M[0])
    # Work on a copy
    A = [list(row) for row in M]
    pivot_row = 0
    for col in range(cols):
        if pivot_row >= rows:
            break
        # Find pivot
        max_row = pivot_row
        for r in range(pivot_row + 1, rows):
            if abs(A[r][col]) > abs(A[max_row][col]):
                max_row = r
        if abs(A[max_row][col]) < tol:
            continue
        A[pivot_row], A[max_row] = A[max_row], A[pivot_row]
        # Eliminate below
        for r in range(pivot_row + 1, rows):
            if abs(A[r][col]) < tol:
                continue
            factor = A[r][col] / A[pivot_row][col]
            for c in range(col, cols):
                A[r][c] -= factor * A[pivot_row][c]
        pivot_row += 1
    rank = pivot_row
    return cols - rank


# ---------------------------------------------------------------------------
# RelationalComplex — 单纯复形管理
# ---------------------------------------------------------------------------


class RelationalComplex:
    """有限抽象单纯复形，用于多关系拓扑建模。

    顶点 0 始终是 agent（自身）。顶点 1..N 是交互对象。
    所有边和三角形都必须包含顶点 0（以 agent 为中心）。

    拓扑结构：
    - 顶点：agent + 各交互对象
    - 边 (0, i)：agent 与对象 i 的二元关系
    - 三角形 (0, i, j)：agent 同时与 i、j 共处的三元关系
    """

    __slots__ = ("_vertices", "_edges", "_triangles")

    def __init__(self) -> None:
        self._vertices: list[int] = [0]  # agent 始终存在
        self._edges: list[tuple[int, int]] = []  # (0, partner_idx) 形式的边
        self._triangles: list[tuple[int, int, int]] = []  # (0, i, j) 形式的三角形

    @property
    def n_vertices(self) -> int:
        return len(self._vertices)

    @property
    def n_edges(self) -> int:
        return len(self._edges)

    @property
    def n_triangles(self) -> int:
        return len(self._triangles)

    def add_partner(self, partner_idx: int) -> None:
        """添加一个交互对象顶点及其与 agent 的边 (0, partner_idx)。"""
        if partner_idx == 0:
            return
        if partner_idx not in self._vertices:
            self._vertices.append(partner_idx)
        edge = (0, partner_idx)
        if edge not in self._edges:
            self._edges.append(edge)

    def add_triangle(self, i: int, j: int) -> None:
        """添加三角形 (0, i, j)——要求两条边都已存在。"""
        if i == 0 or j == 0 or i == j:
            return
        self.add_partner(i)
        self.add_partner(j)
        tri = (0, min(i, j), max(i, j))
        if tri not in self._triangles:
            self._triangles.append(tri)

    def remove_partner(self, partner_idx: int) -> None:
        """移除一个交互对象及其所有关联的单纯形。"""
        if partner_idx == 0 or partner_idx not in self._vertices:
            return
        self._vertices.remove(partner_idx)
        self._edges = [e for e in self._edges if e[1] != partner_idx]
        self._triangles = [t for t in self._triangles if partner_idx not in t]

    def edge_index(self, partner_idx: int) -> int:
        """获取边 (0, partner_idx) 在边列表中的索引。不存在返回 -1。"""
        edge = (0, partner_idx)
        return self._edges.index(edge) if edge in self._edges else -1

    def partners(self) -> list[int]:
        """返回所有交互对象的顶点索引列表。"""
        return [v for v in self._vertices if v != 0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "vertices": list(self._vertices),
            "edges": [list(e) for e in self._edges],
            "triangles": [list(t) for t in self._triangles],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RelationalComplex":
        rc = cls()
        rc._vertices = list(data.get("vertices", [0]))
        rc._edges = [tuple(e) for e in data.get("edges", [])]
        rc._triangles = [tuple(t) for t in data.get("triangles", [])]
        return rc


# ---------------------------------------------------------------------------
# ScarSheaf — 主层结构
# ---------------------------------------------------------------------------

# 茎空间维度
_VERTEX_STALK_DIM = 8  # agent 内部状态（与 scar n_dims 匹配）
_EDGE_STALK_DIM = 8  # 每段关系的 scar 状态引用
_TRIANGLE_STALK_DIM = 4  # 共处状态（降维表示）


class ScarSheaf:
    """关系复形上的胞腔层，用于多关系 Scar 动力学。

    管理：
      - 茎（Stalks）：顶点茎（agent 核心）、边茎（每段关系）、三角形茎（共处）
      - 表示矩阵 P_i（限制映射）：决定 agent 内部状态如何投射到各关系中
      - 上边界算子和层拉普拉斯算子
      - 传播动力学和上同调计算

    核心概念：
    - 表示矩阵 P_i 决定"在关系 i 中暴露自我的哪些维度"
    - H^1 维度 = 不可约的关系矛盾数量
    - 谱间隙 = 关系网络的连通性度量
    - 能量系统限制传播的总量（防止无限扩散）

    与其他组件的关系：
    - 被 body.py 的主循环在每次交互时调用 tick()
    - observe() 输出供计算栈和社交场域使用
    - 人格系统通过 derive_params() 影响所有参数
    """

    __slots__ = (
        "complex",
        "_vertex_stalk",
        "_edge_stalks",
        "_triangle_stalks",
        "_presentation_matrices",
        "_rel_types",
        "_maturities",
        "_personality",
        "_kappa",
        "_energy",
        "_max_energy",
        "_propagation_rate",
        "_tick",
        "_last_timestamp",
        "_propagation_state",
        "_energy_costs",
        "_cached_h1",
        "_cached_dissoc",
        "_cache_tick",
    )

    def __init__(
        self,
        n0: int = _VERTEX_STALK_DIM,
        propagation_rate: float = 0.15,
        max_energy: float = 1.0,
    ) -> None:
        self.complex = RelationalComplex()
        # 顶点茎：agent 的内部状态向量
        self._vertex_stalk: list[float] = [0.0] * n0
        # 边茎：每段关系的状态向量
        self._edge_stalks: list[list[float]] = []
        # 三角形茎：共处状态向量
        self._triangle_stalks: list[list[float]] = []
        # 表示矩阵 P_i (n0 x edge_dim)：决定内部状态如何投射到各关系
        self._presentation_matrices: list[list[list[float]]] = []
        # 关系元数据
        self._rel_types: list[int] = []  # 关系类型
        self._maturities: list[float] = []  # 关系成熟度 [0,1]
        # 人格驱动参数
        self._personality: dict[str, float] = {}
        self._kappa: float = 0.5  # 一致性约束上界
        # 能量系统（公理 S5：传播消耗能量，防止无限扩散）
        self._energy: float = max_energy
        self._max_energy: float = max_energy
        self._energy_costs: list[float] = []  # 每段关系的传播能量消耗
        # 传播状态
        self._propagation_rate: float = propagation_rate
        self._propagation_state: list[float] = [0.0] * n0  # 传播幅度观测
        self._tick: int = 0
        self._last_timestamp: float = 0.0
        # 上同调缓存（计算昂贵，每 N 步重算一次）
        self._cached_h1: int = 0
        self._cached_dissoc: float = 0.0
        self._cache_tick: int = -1

    # ------------------------------------------------------------------
    # 关系管理
    # ------------------------------------------------------------------

    def add_relationship(
        self,
        partner_idx: int,
        rel_type: int | str = FRIENDLY,
        maturity: float = 0.0,
    ) -> None:
        """在层中注册一段新关系（边）。"""
        if isinstance(rel_type, str):
            rel_type = _rel_type_from_str(rel_type)
        self.complex.add_partner(partner_idx)
        edge_idx = self.complex.edge_index(partner_idx)
        # Ensure stalks/matrices are sized correctly
        while len(self._edge_stalks) <= edge_idx:
            self._edge_stalks.append([0.0] * _EDGE_STALK_DIM)
            self._rel_types.append(FRIENDLY)
            self._maturities.append(0.0)
            self._energy_costs.append(0.1)
            self._presentation_matrices.append(
                _mat_zeros(_VERTEX_STALK_DIM, _EDGE_STALK_DIM)
            )
        self._rel_types[edge_idx] = rel_type
        self._maturities[edge_idx] = max(0.0, min(1.0, maturity))
        # Recompute presentation matrix for this relationship
        self._rebuild_presentation_matrix(edge_idx)

    def remove_relationship(self, partner_idx: int) -> None:
        """从层中移除一段关系。"""
        edge_idx = self.complex.edge_index(partner_idx)
        if edge_idx < 0:
            return
        self.complex.remove_partner(partner_idx)
        # Remove corresponding stalks/matrices
        if edge_idx < len(self._edge_stalks):
            self._edge_stalks.pop(edge_idx)
            self._rel_types.pop(edge_idx)
            self._maturities.pop(edge_idx)
            self._energy_costs.pop(edge_idx)
            self._presentation_matrices.pop(edge_idx)
        # Rebuild triangle stalks
        self._triangle_stalks = [
            [0.0] * _TRIANGLE_STALK_DIM for _ in range(self.complex.n_triangles)
        ]

    def set_maturity(self, partner_idx: int, maturity: float) -> None:
        """更新关系成熟度并重建其表示矩阵。"""
        edge_idx = self.complex.edge_index(partner_idx)
        if edge_idx < 0:
            return
        self._maturities[edge_idx] = max(0.0, min(1.0, maturity))
        self._rebuild_presentation_matrix(edge_idx)

    # ------------------------------------------------------------------
    # 人格驱动的参数初始化（定义 6）
    # ------------------------------------------------------------------

    def derive_params(self, personality: dict[str, float]) -> None:
        """从人格向量初始化层参数。

        接受旧版 Big Five 和新版 Embodiment Five 名称。
        映射关系：
          - extraversion/expression_drive_trait → 基线暴露秩（表示矩阵的有效维度）
          - agreeableness/relational_gravity → 降低 kappa（更一致）
          - neuroticism/perception_acuity → 升高 kappa（更多变）
          - openness/boundary_permeability → 更宽的三角形茎耦合
          - conscientiousness/inner_order → 更紧的能量管理
        """
        self._personality = dict(personality)
        e = float(
            personality.get(
                "extraversion", personality.get("expression_drive_trait", 0.5)
            )
        )
        a = float(
            personality.get("agreeableness", personality.get("relational_gravity", 0.5))
        )
        n = float(
            personality.get("neuroticism", personality.get("perception_acuity", 0.5))
        )
        o = float(
            personality.get("openness", personality.get("boundary_permeability", 0.5))
        )
        c = float(
            personality.get("conscientiousness", personality.get("inner_order", 0.5))
        )

        # 一致性约束 kappa(pi)——人格一致性公理
        # 高宜人性→低 kappa（各关系表现更一致）；高神经质→高 kappa（更多变）
        self._kappa = 0.2 + n * 0.6 - a * 0.3
        self._kappa = max(0.05, min(1.0, self._kappa))

        # 传播速率：外向者传播更快（更多开放通道）
        self._propagation_rate = 0.05 + e * 0.2 + o * 0.1

        # 能量管理：高尽责性→更高效（更低基础消耗）
        base_cost = 0.15 - c * 0.08
        for i in range(len(self._energy_costs)):
            self._energy_costs[i] = max(0.02, base_cost)

        # 用新人格参数重建所有表示矩阵
        for i in range(len(self._presentation_matrices)):
            self._rebuild_presentation_matrix(i)

    def _rebuild_presentation_matrix(self, edge_idx: int) -> None:
        """计算 P_i = P_base(pi) + Delta_P(tau_i) + m_i * Delta_P_mature。

        表示矩阵决定 agent 内部状态如何投射到每段关系的可观测空间。
        三个组成部分：
        - P_base：人格决定的基线暴露（外向→更多维度暴露）
        - Delta_P(tau_i)：关系类型调制（亲密→全维暴露，正式→仅表面）
        - Delta_P_mature：成熟度缩放（越成熟→越接近真实自我）
        """
        n0 = _VERTEX_STALK_DIM
        ne = _EDGE_STALK_DIM
        e = float(self._personality.get("extraversion", 0.5))
        o = float(self._personality.get("openness", 0.5))
        n = float(self._personality.get("neuroticism", 0.5))

        rel_type = (
            self._rel_types[edge_idx] if edge_idx < len(self._rel_types) else FRIENDLY
        )
        maturity = (
            self._maturities[edge_idx] if edge_idx < len(self._maturities) else 0.0
        )

        # P_base：人格决定基线秩
        # 外向性→更多维度暴露（对角线值更高）
        P = _mat_zeros(n0, ne)
        base_rank = max(2, int(2 + e * 5))  # 有效维度 2..7
        for d in range(min(base_rank, n0, ne)):
            P[d][d] = 0.3 + e * 0.4  # 对角线强度
        # 开放性添加非对角耦合（跨维度暴露）
        if o > 0.4:
            for d in range(min(n0, ne) - 1):
                P[d][d + 1] = (o - 0.4) * 0.3

        # Delta_P(tau_i)：关系类型调制
        if rel_type == INTIMATE:
            # 亲密：暴露脆弱维度（高对角线，满秩）
            for d in range(min(n0, ne)):
                P[d][d] += 0.3
            # 神经质维度在亲密关系中更可见
            if n0 > 3:
                P[3][3] += n * 0.2
        elif rel_type == FRIENDLY:
            # 友好：适度暴露，社交维度突出
            for d in range(min(3, n0, ne)):
                P[d][d] += 0.15
        elif rel_type == FORMAL:
            # 正式：受限暴露，仅表面维度
            for d in range(min(2, n0, ne)):
                P[d][d] += 0.1
            # 抑制深层维度
            for d in range(3, min(n0, ne)):
                P[d][d] *= 0.3
        elif rel_type == ADVERSARIAL:
            # 对抗：防御性投射，扭曲
            for d in range(min(n0, ne)):
                P[d][d] *= 0.5
            if n0 > 0 and ne > 0:
                P[0][0] += 0.4  # 在维度 0 上投射力量

        # Delta_P_mature：成熟度缩放（更成熟→更接近真实自我）
        if maturity > 0.0:
            for d in range(min(n0, ne)):
                target = 0.8 + e * 0.2
                current = P[d][d]
                P[d][d] = current + maturity * (target - current) * 0.5

        # Clamp values to [-1, 1]
        for i in range(n0):
            for j in range(ne):
                P[i][j] = max(-1.0, min(1.0, P[i][j]))

        self._presentation_matrices[edge_idx] = P

    # ------------------------------------------------------------------
    # 上边界算子（定义 3）
    # ------------------------------------------------------------------

    def _coboundary_0_at_edge(self, edge_idx: int) -> list[float]:
        """计算 (delta^0 x)_e = P_i^T * x_0 - x_i^(ext)。

        返回边 edge_idx 处的上边界向量。
        外部信号 x_i^(ext) 就是边茎本身。
        上边界度量"agent 内部状态投射到关系中"与"关系实际状态"的差异。
        """
        if edge_idx >= len(self._presentation_matrices):
            return [0.0] * _EDGE_STALK_DIM
        P_i = self._presentation_matrices[edge_idx]
        P_iT = _mat_transpose(P_i)
        # P_i is (n0 x ne), P_iT is (ne x n0)
        projected = _mat_vec(P_iT, self._vertex_stalk)
        ext = (
            self._edge_stalks[edge_idx]
            if edge_idx < len(self._edge_stalks)
            else [0.0] * _EDGE_STALK_DIM
        )
        return _vec_sub(projected, ext)

    def coboundary_0(self) -> list[list[float]]:
        """完整 delta^0：返回每条边的上边界向量列表。"""
        return [self._coboundary_0_at_edge(i) for i in range(self.complex.n_edges)]

    def _coboundary_1_at_triangle(self, tri_idx: int) -> list[float]:
        """计算三角形处的 (delta^1 s)_sigma。

        对于三角形 (0, i, j)：
        度量两条边茎从共处上下文看是否一致。
        不一致意味着"在 i 面前和在 j 面前表现矛盾"。
        """
        if tri_idx >= self.complex.n_triangles:
            return [0.0] * _TRIANGLE_STALK_DIM
        tri = self.complex._triangles[tri_idx]
        # tri = (0, i, j)
        edge_i_idx = self.complex.edge_index(tri[1])
        edge_j_idx = self.complex.edge_index(tri[2])
        if edge_i_idx < 0 or edge_j_idx < 0:
            return [0.0] * _TRIANGLE_STALK_DIM

        # Project edge stalks to triangle dimension (take first _TRIANGLE_STALK_DIM dims)
        si = self._edge_stalks[edge_i_idx][:_TRIANGLE_STALK_DIM]
        sj = self._edge_stalks[edge_j_idx][:_TRIANGLE_STALK_DIM]
        tri_stalk = (
            self._triangle_stalks[tri_idx]
            if tri_idx < len(self._triangle_stalks)
            else [0.0] * _TRIANGLE_STALK_DIM
        )

        # Pad if needed
        while len(si) < _TRIANGLE_STALK_DIM:
            si.append(0.0)
        while len(sj) < _TRIANGLE_STALK_DIM:
            sj.append(0.0)

        # delta^1 = (si projected) - tri_stalk + (sj projected)
        # Measures whether the triangle stalk is consistent with its face edges
        result = [0.0] * _TRIANGLE_STALK_DIM
        for d in range(_TRIANGLE_STALK_DIM):
            result[d] = si[d] - tri_stalk[d] + sj[d]
        return result

    def coboundary_1(self) -> list[list[float]]:
        """完整 delta^1：返回每个三角形的上边界向量列表。"""
        return [
            self._coboundary_1_at_triangle(i) for i in range(self.complex.n_triangles)
        ]

    # ------------------------------------------------------------------
    # 层拉普拉斯算子（定义 4）
    # ------------------------------------------------------------------

    def _sheaf_laplacian_at_vertex(self) -> list[float]:
        """计算顶点处的层拉普拉斯 L_F(x_0)。

        L_F = sum_i P_i P_i^T（形状 n0 x n0），是顶点茎上的二次型。
        仿射项 P_i * s_i 将边信号通过伴随映射投射回顶点空间。

        返回拉普拉斯作用于顶点茎的结果向量。
        """
        n0 = len(self._vertex_stalk)
        result = [0.0] * n0

        for i in range(self.complex.n_edges):
            if i >= len(self._presentation_matrices):
                break
            P_i = self._presentation_matrices[i]
            P_iT = _mat_transpose(P_i)
            # P_i P_i^T x_0  (vertex Laplacian: n0 x n0)
            PPt = _mat_mul(P_i, P_iT)
            PPt_x = _mat_vec(PPt, self._vertex_stalk)
            # P_i * edge_stalk_i (project edge signal back to vertex space)
            edge_stalk = (
                self._edge_stalks[i]
                if i < len(self._edge_stalks)
                else [0.0] * _EDGE_STALK_DIM
            )
            P_s = _mat_vec(P_i, edge_stalk)
            # Accumulate
            for d in range(n0):
                result[d] += PPt_x[d] - P_s[d]

        return result

    def sheaf_laplacian_matrix(self) -> list[list[float]]:
        """构建完整的层拉普拉斯矩阵 L_F = sum_i P_i P_i^T。

        返回 n0 x n0 矩阵（二次型部分）。
        """
        n0 = len(self._vertex_stalk)
        L = _mat_zeros(n0, n0)
        for i in range(self.complex.n_edges):
            if i >= len(self._presentation_matrices):
                break
            P_i = self._presentation_matrices[i]
            P_iT = _mat_transpose(P_i)
            PPt = _mat_mul(P_i, P_iT)
            L = _mat_add(L, PPt)
        return L

    def spectral_gap(self) -> float:
        """计算层拉普拉斯的谱间隙 lambda_1 / lambda_max。

        谱间隙度量关系网络的连通性：
        - 高谱间隙 = 关系间信息流通顺畅
        - 低谱间隙 = 关系间相互隔离

        关系数 < 2 时返回 0.0。
        """
        if self.complex.n_edges < 2:
            return 0.0
        L = self.sheaf_laplacian_matrix()
        eigenvalues = _eigenvalues_symmetric(L)
        if len(eigenvalues) < 2:
            return 0.0
        # Find first non-zero eigenvalue
        lambda_max = max(abs(eigenvalues[-1]), 1e-12)
        for ev in eigenvalues:
            if ev > 1e-8:
                return ev / lambda_max
        return 0.0

    # ------------------------------------------------------------------
    # 上同调计算（定义 5）
    # ------------------------------------------------------------------

    def compute_h1(self) -> int:
        """计算 dim H^1(K, F)——不一致性维度。

        H^1 = ker(delta^1) / im(delta^0)。
        直觉：H^1 的每个维度代表一个"不可通过局部调整消除的关系矛盾"。

        返回:
            非负整数：不可约关系矛盾的数量。
        """
        n_edges = self.complex.n_edges
        if n_edges == 0:
            return 0

        # Build delta^0 as a matrix: rows = edge_dim * n_edges, cols = n0
        # Each block row i is P_i^T (ne x n0 → maps vertex stalk to edge space)
        n0 = len(self._vertex_stalk)
        ne = _EDGE_STALK_DIM

        # delta^0 matrix: (n_edges * ne) x n0
        d0_rows = n_edges * ne
        d0 = _mat_zeros(d0_rows, n0)
        for i in range(n_edges):
            if i >= len(self._presentation_matrices):
                break
            P_iT = _mat_transpose(self._presentation_matrices[i])
            for r in range(ne):
                for c in range(n0):
                    d0[i * ne + r][c] = P_iT[r][c]

        # Rank of delta^0 = rank of im(delta^0)
        rank_d0 = d0_rows - _kernel_dim(d0)

        # If no triangles, H^1 = n_edges * ne - rank(d0) - (n_edges * ne - rank_d0)
        # Simplified: H^1 = dim(C^1) - rank(d0) when no delta^1
        n_triangles = self.complex.n_triangles
        if n_triangles == 0:
            # H^1 = dim(ker(delta^1=0)) / im(delta^0) = dim(C^1) - rank(d0)
            # But C^1 = n_edges * ne, and without delta^1 everything is in ker
            dim_c1 = n_edges * ne
            h1 = max(0, dim_c1 - rank_d0)
            return h1

        # Build delta^1 matrix: (n_triangles * tri_dim) x (n_edges * ne)
        tri_dim = _TRIANGLE_STALK_DIM
        d1_rows = n_triangles * tri_dim
        d1_cols = n_edges * ne
        d1 = _mat_zeros(d1_rows, d1_cols)
        for t_idx in range(n_triangles):
            tri = self.complex._triangles[t_idx]
            edge_i_idx = self.complex.edge_index(tri[1])
            edge_j_idx = self.complex.edge_index(tri[2])
            if edge_i_idx < 0 or edge_j_idx < 0:
                continue
            # Restriction from edge_i to triangle: take first tri_dim dims
            for d in range(tri_dim):
                if edge_i_idx * ne + d < d1_cols:
                    d1[t_idx * tri_dim + d][edge_i_idx * ne + d] = 1.0
                if edge_j_idx * ne + d < d1_cols:
                    d1[t_idx * tri_dim + d][edge_j_idx * ne + d] = 1.0

        # dim(ker(delta^1))
        ker_d1 = _kernel_dim(d1)
        # But _kernel_dim returns cols - rank, which IS dim(ker)
        # H^1 = dim(ker(d1)) - rank(d0)
        h1 = max(0, ker_d1 - rank_d0)
        return h1

    def inconsistency_vector(self) -> list[float]:
        """计算阻碍上循环——每条边的实际不一致性。

        返回长度为 n_edges 的向量，每个元素是该边上边界的范数。
        值越高表示该关系的不一致性越大。
        """
        cb = self.coboundary_0()
        return [_vec_norm(v) for v in cb]

    def dissociation_pressure(self) -> float:
        """标量解离压力（带缓存，公理 S3）。"""
        if self._cache_tick == self._tick:
            return self._cached_dissoc
        return self._dissociation_pressure_uncached()

    def _dissociation_pressure_uncached(self) -> float:
        """标量解离压力（无缓存版本，公理 S3）。

        综合三个因素：
          - H^1 维度（不可约矛盾数）
          - 总不一致性能量
          - 谱间隙（隔离度量）

        返回:
            [0, 1] 范围的浮点数，1 = 最大解离压力。
        """
        if self.complex.n_edges == 0:
            return 0.0

        # Inconsistency energy: sum of squared coboundary norms
        incon_vec = self.inconsistency_vector()
        incon_energy = sum(x * x for x in incon_vec)

        # Normalize by number of edges and stalk dimension
        n_edges = self.complex.n_edges
        max_possible = n_edges * _EDGE_STALK_DIM  # rough upper bound
        normalized_incon = min(1.0, incon_energy / max(1.0, max_possible))

        # H^1 contribution (each dimension adds pressure)
        h1 = self.compute_h1()
        h1_pressure = min(1.0, h1 / max(1.0, n_edges * 2.0))

        # Spectral gap: low gap → high isolation → more pressure
        gap = self.spectral_gap()
        gap_pressure = max(0.0, 1.0 - gap * 2.0)

        # Weighted combination
        pressure = 0.4 * normalized_incon + 0.35 * h1_pressure + 0.25 * gap_pressure
        return max(0.0, min(1.0, pressure))

    # ------------------------------------------------------------------
    # 传播动力学（公理 S2, S4）
    # ------------------------------------------------------------------

    def propagate(
        self,
        source_idx: int,
        scar_event: list[float],
        dt: float = 1.0,
    ) -> dict[str, Any]:
        """通过拉普拉斯扩散将 scar 影响从源关系传播到其他关系。

        实现公理 S2：
          dx_0/dt = -alpha * L_F(x_0) + f_local(t)

        和公理 S4：传播效果不可逆。

        参数:
            source_idx: 源关系的边索引
            scar_event: scar 事件向量（在边茎空间中）
            dt: 扩散时间步长

        返回:
            包含传播详情的字典
        """
        if source_idx < 0 or source_idx >= self.complex.n_edges:
            return {"propagated": False, "reason": "invalid_source"}

        # Energy check (Axiom S5)
        cost = (
            self._energy_costs[source_idx]
            if source_idx < len(self._energy_costs)
            else 0.1
        )
        if self._energy < cost * dt:
            return {"propagated": False, "reason": "energy_depleted"}

        # Consume energy
        self._energy = max(0.0, self._energy - cost * dt)

        # Inject scar event into source edge stalk
        edge_stalk = self._edge_stalks[source_idx]
        for d in range(min(len(scar_event), len(edge_stalk))):
            edge_stalk[d] += scar_event[d]
            # Clamp to [-2, 2] for stability
            edge_stalk[d] = max(-2.0, min(2.0, edge_stalk[d]))

        # Compute Laplacian diffusion on vertex stalk
        L_x = self._sheaf_laplacian_at_vertex()
        alpha = self._propagation_rate

        # Local forcing: project source event to vertex space via P_source^T
        if source_idx < len(self._presentation_matrices):
            P_s = self._presentation_matrices[source_idx]
            # P_s is (n0 x ne), we want P_s @ scar_event → n0-dim
            f_local = _mat_vec(
                P_s,
                scar_event[:_EDGE_STALK_DIM]
                + [0.0] * max(0, _EDGE_STALK_DIM - len(scar_event)),
            )
        else:
            f_local = [0.0] * len(self._vertex_stalk)

        # Euler step: x_0 += dt * (-alpha * L_x + f_local)
        n0 = len(self._vertex_stalk)
        affected_dims: list[int] = []
        for d in range(n0):
            delta = dt * (-alpha * L_x[d] + f_local[d])
            if abs(delta) > 1e-6:
                affected_dims.append(d)
            self._vertex_stalk[d] += delta
            # Clamp for stability
            self._vertex_stalk[d] = max(-2.0, min(2.0, self._vertex_stalk[d]))

        # Propagate to other edge stalks (exponential decay with distance)
        propagated_to: list[int] = []
        for i in range(self.complex.n_edges):
            if i == source_idx:
                continue
            if i >= len(self._edge_stalks):
                break
            # Combinatorial distance is always 2 (source_edge → vertex → target_edge)
            decay = math.exp(-2.0 * alpha)
            if i >= len(self._presentation_matrices):
                continue
            P_i = self._presentation_matrices[i]
            # Project vertex change into edge space: P_i^T @ delta_vertex
            delta_vertex = [dt * (-alpha * L_x[d] + f_local[d]) for d in range(n0)]
            P_iT = _mat_transpose(P_i)
            edge_delta = _mat_vec(P_iT, delta_vertex)
            # Apply with decay
            propagated = False
            for d in range(len(self._edge_stalks[i])):
                contribution = edge_delta[d] * decay if d < len(edge_delta) else 0.0
                if abs(contribution) > 1e-8:
                    self._edge_stalks[i][d] += contribution
                    self._edge_stalks[i][d] = max(
                        -2.0, min(2.0, self._edge_stalks[i][d])
                    )
                    propagated = True
            if propagated:
                propagated_to.append(i)

        # Update propagation state (for observation) with decay to prevent unbounded growth
        self._propagation_state = [
            self._propagation_state[d] * 0.95 + abs(dt * (-alpha * L_x[d] + f_local[d]))
            for d in range(n0)
        ]

        return {
            "propagated": True,
            "source": source_idx,
            "affected_dims": affected_dims,
            "propagated_to": propagated_to,
            "energy_remaining": self._energy,
            "decay_factor": math.exp(-2.0 * alpha),
        }

    # ------------------------------------------------------------------
    # 集成接口
    # ------------------------------------------------------------------

    def tick(
        self,
        active_relationship_idx: int,
        event_vec: list[float],
        timestamp: float = 0.0,
    ) -> dict[str, Any]:
        """主入口：在关系层中处理一个事件。

        参数:
            active_relationship_idx: 当前活跃关系的边索引
            event_vec: 事件向量（来自 Scar Algebra，在边茎空间中）
            timestamp: 事件时间戳

        返回:
            包含传播结果、上同调状态、能量的字典
        """
        self._tick += 1

        # Compute dt from timestamp
        dt = 1.0
        if self._last_timestamp > 0.0 and timestamp > self._last_timestamp:
            dt = min(10.0, (timestamp - self._last_timestamp))
        self._last_timestamp = timestamp

        # Energy regeneration (slow, capped at max)
        regen = 0.01 * dt
        self._energy = min(self._max_energy, self._energy + regen)

        # Maturity growth for active relationship
        if 0 <= active_relationship_idx < len(self._maturities):
            growth = 0.001 * dt
            old_mat = self._maturities[active_relationship_idx]
            new_mat = min(1.0, old_mat + growth)
            if new_mat != old_mat:
                self._maturities[active_relationship_idx] = new_mat
                # Rebuild P_i only if maturity changed significantly
                if new_mat - old_mat > 0.01:
                    self._rebuild_presentation_matrix(active_relationship_idx)

        # Propagate the event
        prop_result = self.propagate(active_relationship_idx, event_vec, dt)

        # Presentation matrix evolution (Axiom S6)
        # Gradient step toward consistency — run every 3 ticks for performance
        if self._tick % 3 == 0:
            self._evolve_presentation_matrices(dt * 3.0)

        # Cohomology cache: recompute every 5 ticks (expensive)
        if self._tick - self._cache_tick >= 5:
            self._cached_dissoc = self._dissociation_pressure_uncached()
            self._cached_h1 = self.compute_h1()
            self._cache_tick = self._tick

        return {
            "tick": self._tick,
            "propagation": prop_result,
            "energy": self._energy,
            "dissociation_pressure": self._cached_dissoc,
            "timestamp": timestamp,
        }

    def _evolve_presentation_matrices(self, dt: float) -> None:
        """公理 S6：表示矩阵向一致性方向演化。

        P_i(t+1) = P_i(t) + eta * grad_Pi(L_consistency)
        简化梯度：推动 P_i 减小其上边界范数，受 kappa 约束。
        """
        eta = 0.005 * dt  # learning rate
        cb = self.coboundary_0()

        for i in range(min(len(self._presentation_matrices), len(cb))):
            if i >= len(self._edge_stalks):
                break
            P_i = self._presentation_matrices[i]
            n0 = len(P_i)
            ne = len(P_i[0]) if n0 > 0 else 0

            # Gradient of ||P_i^T x_0 - s_i||^2 w.r.t. P_i
            # = 2 * x_0 @ (P_i^T x_0 - s_i)^T = 2 * x_0 @ cb_i^T
            # Simplified: outer product x_0 * cb_i
            cb_i = cb[i]
            for r in range(n0):
                for c in range(ne):
                    if c < len(cb_i):
                        grad = self._vertex_stalk[r] * cb_i[c]
                        P_i[r][c] -= eta * grad
                        P_i[r][c] = max(-1.0, min(1.0, P_i[r][c]))

        # Enforce consistency bound kappa between all pairs
        self._enforce_kappa()

    def _enforce_kappa(self) -> None:
        """强制执行 ||P_i - P_j||_F <= kappa * (1 + d(tau_i, tau_j))。

        确保不同关系的表示矩阵差异不超过人格一致性约束。
        关系类型差异越大，允许的矩阵差异越大。
        """
        n = len(self._presentation_matrices)
        if n < 2:
            return
        kappa = self._kappa
        rel_types = self._rel_types
        matrices = self._presentation_matrices
        for i in range(n):
            Pi = matrices[i]
            rows = len(Pi)
            cols = len(Pi[0]) if rows > 0 else 0
            ti = rel_types[i] if i < len(rel_types) else FRIENDLY
            for j in range(i + 1, n):
                Pj = matrices[j]
                tj = rel_types[j] if j < len(rel_types) else FRIENDLY
                type_dist = abs(ti - tj)
                bound = kappa * (1.0 + type_dist)
                # Compute Frobenius norm squared inline
                norm_sq = 0.0
                for r in range(rows):
                    Pi_r = Pi[r]
                    Pj_r = Pj[r]
                    for c in range(cols):
                        d = Pi_r[c] - Pj_r[c]
                        norm_sq += d * d
                if norm_sq <= bound * bound or norm_sq < 1e-20:
                    continue
                # Project toward bound
                norm = math.sqrt(norm_sq)
                mid_scale = (1.0 - bound / norm) * 0.5
                for r in range(rows):
                    Pi_r = Pi[r]
                    Pj_r = Pj[r]
                    for c in range(cols):
                        adjustment = (Pi_r[c] - Pj_r[c]) * mid_scale
                        Pi_r[c] -= adjustment
                        Pj_r[c] += adjustment

    def observe(self) -> dict[str, Any]:
        """生成可观测输出，供下游层使用。

        返回:
            包含上同调维度、谱间隙、能量、传播状态、
            每段关系不一致性的字典。
        """
        n_edges = self.complex.n_edges
        # Use cached H^1 if available (expensive to compute)
        if self._cache_tick == self._tick:
            h1 = self._cached_h1
            dissoc = self._cached_dissoc
        else:
            h1 = self.compute_h1() if n_edges > 0 else 0
            dissoc = self._dissociation_pressure_uncached()
        gap = self.spectral_gap()
        incon = self.inconsistency_vector()

        return {
            "h1_dim": h1,
            "spectral_gap": round(gap, 6),
            "energy": round(self._energy, 4),
            "max_energy": self._max_energy,
            "dissociation_pressure": round(dissoc, 4),
            "n_relationships": n_edges,
            "n_triangles": self.complex.n_triangles,
            "inconsistency_per_edge": [round(x, 4) for x in incon],
            "propagation_magnitude": round(_vec_norm(self._propagation_state), 4),
            "vertex_stalk_norm": round(_vec_norm(self._vertex_stalk), 4),
            "tick": self._tick,
            "kappa": round(self._kappa, 4),
        }

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """序列化完整层状态用于持久化。"""
        return {
            "complex": self.complex.to_dict(),
            "vertex_stalk": list(self._vertex_stalk),
            "edge_stalks": [list(s) for s in self._edge_stalks],
            "triangle_stalks": [list(s) for s in self._triangle_stalks],
            "presentation_matrices": [
                [list(row) for row in P] for P in self._presentation_matrices
            ],
            "rel_types": list(self._rel_types),
            "maturities": list(self._maturities),
            "personality": dict(self._personality),
            "kappa": self._kappa,
            "energy": self._energy,
            "max_energy": self._max_energy,
            "energy_costs": list(self._energy_costs),
            "propagation_rate": self._propagation_rate,
            "propagation_state": list(self._propagation_state),
            "tick": self._tick,
            "last_timestamp": self._last_timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScarSheaf":
        """从持久化状态恢复层。"""
        sheaf = cls()
        sheaf.complex = RelationalComplex.from_dict(data.get("complex", {}))
        sheaf._vertex_stalk = list(data.get("vertex_stalk", [0.0] * _VERTEX_STALK_DIM))
        sheaf._edge_stalks = [list(s) for s in data.get("edge_stalks", [])]
        sheaf._triangle_stalks = [list(s) for s in data.get("triangle_stalks", [])]
        sheaf._presentation_matrices = [
            [list(row) for row in P] for P in data.get("presentation_matrices", [])
        ]
        sheaf._rel_types = list(data.get("rel_types", []))
        sheaf._maturities = list(data.get("maturities", []))
        sheaf._personality = dict(data.get("personality", {}))
        sheaf._kappa = float(data.get("kappa", 0.5))
        sheaf._energy = float(data.get("energy", 1.0))
        sheaf._max_energy = float(data.get("max_energy", 1.0))
        sheaf._energy_costs = list(data.get("energy_costs", []))
        sheaf._propagation_rate = float(data.get("propagation_rate", 0.15))
        sheaf._propagation_state = list(
            data.get("propagation_state", [0.0] * _VERTEX_STALK_DIM)
        )
        sheaf._tick = int(data.get("tick", 0))
        sheaf._last_timestamp = float(data.get("last_timestamp", 0.0))
        sheaf._cached_h1 = 0
        sheaf._cached_dissoc = 0.0
        sheaf._cache_tick = -1
        return sheaf
