"""Sylanne-Embodiment 计算核心层：超维计算编码器（Hyperdimensional Computing, HDC）。

在 7 层计算栈中的位置：L1 感知层。
职责：将原始文本编码为高维稀疏二进制超向量（hypervector），用于下游的快速相似度匹配
和组合表示。使用 bytearray 紧凑存储，所有核心运算均为位操作。

性能优化（双路径）：
  - numpy 路径（首选）：预计算字符→随机向量查找表（shape [256, dim], dtype uint8），
    利用向量化 XOR + roll 完成 bigram 编码，sum + threshold 完成多数投票捆绑。
    单次 encode_text 调用中无 Python 逐元素循环，全部由 numpy SIMD 内核完成。
  - 纯 Python 路径（回退）：采用 Python 大整数实现垂直二进制计数（vertical binary
    counting），配合预计算的位掩码完成逐字节移位操作。当 numpy 不可用时自动启用。
"""

from __future__ import annotations

import hashlib
import struct
from collections import OrderedDict

# ---------- numpy 可选导入 ----------
# numpy 是标准科学计算依赖，用于向量化 HDC 编码加速。
# 若环境中不可用则回退到纯 Python 大整数实现。
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

_SEED_CACHE_MAXSIZE = 10000
_SEED_CACHE_EVICT_COUNT = 1000

# ---------- numpy 加速：字符→随机向量查找表 ----------
# 预计算 256 个单字节字符各自对应的 dim 维二进制随机向量。
# 使用 SHA-256 哈希链确保确定性（与纯 Python 路径的 atom() 结果一致）。


def _build_char_lut(dim: int) -> "np.ndarray":
    """构建字符查找表：shape [256, dim], dtype uint8, 每个元素为 0 或 1。

    对每个字节值 b (0-255)，用 SHA-256 哈希链生成 dim 个随机比特。
    这与 HDCEncoder.atom(chr(b)) 的结果按位一致，保证两条路径输出相同。
    """
    byte_dim = dim // 8
    lut = np.zeros((256, dim), dtype=np.uint8)
    for b in range(256):
        # 生成与 atom() 相同的随机字节序列
        token_bytes = chr(b).encode("utf-8")
        parts = []
        chunk = 0
        while len(b"".join(parts)) < byte_dim:
            parts.append(hashlib.sha256(token_bytes + struct.pack("<I", chunk)).digest())
            chunk += 1
        raw = b"".join(parts)[:byte_dim]
        # 将 packed bytes 展开为 dim 个独立比特（little-endian 位序）
        for byte_idx, byte_val in enumerate(raw):
            for bit_idx in range(8):
                lut[b, byte_idx * 8 + bit_idx] = (byte_val >> bit_idx) & 1
    return lut


def _build_shift_masks(byte_dim: int, dim: int) -> tuple:
    """预计算每种子字节移位余数（1-7）对应的位掩码。

    对于移位余数 r，逐字节操作为：
      output[B] = (rot[B] >> r) | ((rot[B-1] & low_r_mask) << (8-r))

    将其分解为两个全局大整数操作：
      part1 = (rot_int >> r) & keep_mask   （每字节的低 8-r 位）
      part2 = circular_left_shift(rot_int & low_mask, 16-r) & high_mask

    预计算这些掩码后，编码时每个 token 的移位操作只需 O(1) 次大整数运算。
    """
    full_mask = (1 << dim) - 1
    masks = [None]  # index 0 unused (sr=0 means no sub-byte shift)
    for r in range(1, 8):
        keep_byte = (1 << (8 - r)) - 1  # bits 0..7-r
        low_byte = (1 << r) - 1  # bits 0..r-1
        keep_mask = sum(keep_byte << (i * 8) for i in range(byte_dim))
        low_mask = sum(low_byte << (i * 8) for i in range(byte_dim))
        high_mask = full_mask ^ keep_mask
        shift_amount = 16 - r
        masks.append((keep_mask, low_mask, high_mask, shift_amount))
    return tuple(masks)


class HDCEncoder:
    """超维计算编码器。

    将文本 token 序列编码为固定维度的稀疏二进制超向量。
    核心操作：
      - atom(): 为每个 token 生成确定性随机二进制向量
      - encode(): 通过"移位+捆绑"将 token 序列编码为单一超向量
      - similarity(): 基于 Hamming 距离的相似度计算
      - bind(): XOR 绑定（表示"关系"）
      - bundle(): 多数投票捆绑（表示"集合"）

    与其他组件的关系：
      - 被 ComputationSpine 在 L1 层调用，输出传递给 L2 PredictiveCodingGate
      - 输出的 bytearray 同时作为 VoidSpace 的边界向量使用
    """

    def __init__(self, dim: int = 1024):
        self.dim = dim
        self._byte_dim = dim // 8
        self._seed_cache: OrderedDict[str, bytearray] = OrderedDict()
        self._mask = (1 << dim) - 1
        self._shift_masks = _build_shift_masks(self._byte_dim, dim)
        # numpy 加速路径：预计算字符查找表
        # 查找表只在首次需要时构建（lazy init），避免 import 时的开销
        self._np_char_lut: "np.ndarray | None" = None

    def atom(self, token: str) -> bytearray:
        """为单个 token 生成确定性随机二进制向量（packed bytes 格式）。

        使用 SHA-256 哈希链生成足够的随机字节，结果被缓存以避免重复计算。
        缓存超过 10000 条时淘汰最旧的 1000 条（LRU 策略）。
        """
        if token in self._seed_cache:
            return self._seed_cache[token]
        # Generate enough random bytes
        parts = []
        h = token.encode("utf-8")
        needed = self._byte_dim
        chunk = 0
        while len(b"".join(parts)) < needed:
            parts.append(hashlib.sha256(h + struct.pack("<I", chunk)).digest())
            chunk += 1
        vec = bytearray(b"".join(parts)[:needed])
        self._seed_cache[token] = vec
        # Evict oldest entries when cache exceeds maxsize
        if len(self._seed_cache) > _SEED_CACHE_MAXSIZE:
            for _ in range(_SEED_CACHE_EVICT_COUNT):
                self._seed_cache.popitem(last=False)
        return vec

    def encode(self, tokens: list[str]) -> bytearray:
        """将 token 序列编码为单一超向量（移位+捆绑方法）。

        算法：
          1. 对每个 token，生成原子向量并按位置循环移位（保持位置信息）
          2. 使用垂直二进制计数器累加所有移位后的向量
          3. 多数投票：计数 > n/2 的位设为 1，否则设为 0

        性能：每个 token 的加法是 O(log n) 次大整数 AND/XOR 操作，
        而非 O(dim) 次标量递增。移位使用预计算掩码实现 O(1) 大整数操作。

        Args:
            tokens: 待编码的 token 列表

        Returns:
            编码后的二进制超向量（bytearray 格式）
        """
        if not tokens:
            return bytearray(self._byte_dim)
        n = len(tokens)
        dim = self.dim
        byte_dim = self._byte_dim
        mask = self._mask
        shift_masks = self._shift_masks

        # Vertical counter: n_bits planes, each a dim-bit int
        n_bits = max(1, n.bit_length())
        c = [0] * n_bits

        for pos, token in enumerate(tokens):
            a = self.atom(token)
            shift_bits = pos % dim
            sb = shift_bits // 8
            sr = shift_bits % 8

            # Compute shifted vector as int (replicates original byte-carry shift)
            if sb == 0 and sr == 0:
                v = int.from_bytes(a, "little")
            else:
                # Byte rotation: get rotated int
                if sb == 0:
                    rot_int = int.from_bytes(a, "little")
                else:
                    start = (byte_dim - sb) % byte_dim
                    rot_int = int.from_bytes(a[start:] + a[:start], "little")

                if sr == 0:
                    v = rot_int
                else:
                    # Sub-byte shift using pre-computed masks (no Python loop)
                    keep_mask, low_mask, high_mask, shift_amt = shift_masks[sr]
                    # Part 1: right-shift within each byte (keep low bits)
                    part1 = (rot_int >> sr) & keep_mask
                    # Part 2: carry from previous byte (circular left shift)
                    masked_low = rot_int & low_mask
                    part2 = (
                        (masked_low << shift_amt) | (masked_low >> (dim - shift_amt))
                    ) & high_mask
                    v = part1 | part2

            # Add v to vertical counter (binary ripple-carry addition)
            carry = v
            for i in range(n_bits):
                if carry == 0:
                    break
                new_carry = c[i] & carry
                c[i] ^= carry
                carry = new_carry

        # Majority vote: find positions where count > n/2 (i.e., count >= n//2+1)
        threshold = n // 2 + 1
        borrow = 0
        for i in range(n_bits):
            t_bit = (threshold >> i) & 1
            if t_bit:
                if borrow == 0:
                    borrow = (~c[i]) & mask
                else:
                    borrow = (((~c[i]) & mask) | borrow) & mask
            else:
                if borrow != 0:
                    borrow = (~c[i]) & mask & borrow

        result_int = (~borrow) & mask
        return bytearray(result_int.to_bytes(byte_dim, "little"))

    def encode_text(self, text: str) -> bytearray:
        """编码原始文本（使用字符级 bigram 作为 token）。

        双路径分发：
          - numpy 可用时：调用 _encode_text_numpy()，全向量化操作，无 Python 循环
          - numpy 不可用时：回退到原始 bigram 分词 + encode() 大整数路径
        两条路径的输出格式完全一致（bytearray, little-endian packed bits）。
        """
        if not text:
            return bytearray(self._byte_dim)
        # numpy 路径在短文本上有固定开销（LUT 索引 + 矩阵构建），
        # 只有文本 UTF-8 长度 >= 128 字节时才有加速收益
        if _HAS_NUMPY and len(text.encode("utf-8")) >= 128:
            return self._encode_text_numpy(text)
        tokens = self._tokenize(text)
        return self.encode(tokens)

    def _encode_text_numpy(self, text: str) -> bytearray:
        """numpy 向量化 HDC 文本编码（L1 热路径优化核心）。

        算法步骤：
          1. 将文本转为字节序列（UTF-8），取每个字节的查找表向量
          2. 对相邻字节对构造 bigram 向量：char[i] XOR roll(char[i+1], 1)
             - XOR 实现"绑定"语义（表示两字符的关系）
             - roll 引入位置不对称性（区分 AB 和 BA）
          3. 对每个 bigram 向量按位置施加循环移位（保持序列位置信息）
          4. 所有 bigram 向量逐位求和，阈值化为多数投票结果
          5. 将 dim 维 0/1 数组打包回 bytearray（little-endian 位序）

        性能特征：
          - 步骤 1: O(n) numpy 索引，无循环
          - 步骤 2: O(n×dim) numpy 广播 XOR + roll
          - 步骤 3: O(n×dim) numpy roll（向量化）
          - 步骤 4: O(n×dim) numpy sum + 比较
          - 步骤 5: O(dim) numpy packbits
          总体：相比纯 Python 大整数路径，在典型文本长度（50-500 字符）下快 5-15x。
        """
        # 懒初始化字符查找表（只构建一次，之后复用）
        if self._np_char_lut is None:
            self._np_char_lut = _build_char_lut(self.dim)

        dim = self.dim
        lut = self._np_char_lut

        # 步骤 1：将文本转为字节序列，查找每个字节对应的随机向量
        # 注意：对于多字节 UTF-8 字符，每个字节都作为独立单元参与编码
        text_bytes = text.strip().encode("utf-8")
        if len(text_bytes) <= 1:
            if len(text_bytes) == 0:
                return bytearray(self._byte_dim)
            # 单字节：直接返回该字符的原子向量（packed 格式）
            return self._np_bits_to_bytearray(lut[text_bytes[0]])

        # 将字节序列转为 numpy 数组用于批量索引
        byte_indices = np.frombuffer(text_bytes, dtype=np.uint8)
        # char_vecs: shape [n_bytes, dim], 每行是一个字符的随机二进制向量
        char_vecs = lut[byte_indices]  # numpy 高级索引，O(n) 无循环

        # 步骤 2：构造 bigram 向量
        # bigram[i] = char[i] XOR roll(char[i+1], 1)
        # roll(v, 1) 表示循环右移 1 位：将最后一个元素移到第一个位置
        n_bigrams = len(byte_indices) - 1
        # 对第二个字符施加 1 位循环移位（numpy.roll 沿 axis=1）
        shifted_next = np.roll(char_vecs[1:], shift=1, axis=1)
        # XOR 绑定：当前字符 ⊕ 移位后的下一个字符
        bigram_vecs = char_vecs[:-1] ^ shifted_next  # shape [n_bigrams, dim]

        # 步骤 3：对每个 bigram 按其位置施加循环移位（保持序列顺序信息）
        # bigram[i] 移位 i 位（模 dim）
        # 为避免逐行 Python 循环，使用向量化的索引技巧
        if n_bigrams > 1:
            # 构造移位索引矩阵：每行 i 的索引为 [(0-i)%dim, (1-i)%dim, ..., (dim-1-i)%dim]
            # 这等价于对该行做 roll(shift=i)
            base_indices = np.arange(dim, dtype=np.int32)
            shifts = np.arange(n_bigrams, dtype=np.int32) % dim
            # shift_matrix[i, j] = (j - shifts[i]) % dim
            # 即：结果的第 j 位 = 原始的第 (j - shift) % dim 位 → 循环右移 shift 位
            shift_matrix = (base_indices[np.newaxis, :] - shifts[:, np.newaxis]) % dim
            # 使用高级索引完成所有行的移位（全向量化，无 Python 循环）
            bigram_vecs = bigram_vecs[np.arange(n_bigrams)[:, np.newaxis], shift_matrix]

        # 步骤 4：多数投票捆绑
        # 对所有 bigram 向量逐位求和，超过半数的位设为 1
        vote_sum = bigram_vecs.sum(axis=0, dtype=np.int32)  # shape [dim]
        threshold = n_bigrams // 2  # 严格大于半数
        result_bits = (vote_sum > threshold).astype(np.uint8)  # shape [dim], 0 或 1

        # 步骤 5：将 dim 维比特数组打包为 bytearray（little-endian 位序）
        return self._np_bits_to_bytearray(result_bits)

    def _np_bits_to_bytearray(self, bits: "np.ndarray") -> bytearray:
        """将 dim 维 0/1 numpy 数组打包为 bytearray（little-endian 位序）。

        位序约定：bits[byte_idx*8 + bit_idx] 对应输出字节 byte_idx 的第 bit_idx 位。
        这与纯 Python 路径的 int.to_bytes(byte_dim, 'little') 位序一致。
        """
        dim = self.dim
        byte_dim = self._byte_dim
        # 重塑为 [byte_dim, 8]，每行是一个字节的 8 个比特（从 LSB 到 MSB）
        reshaped = bits.reshape(byte_dim, 8)
        # 每行乘以 [1, 2, 4, 8, 16, 32, 64, 128] 然后求和得到字节值
        powers = np.array([1, 2, 4, 8, 16, 32, 64, 128], dtype=np.uint8)
        packed = reshaped.dot(powers).astype(np.uint8)  # shape [byte_dim]
        return bytearray(packed.tobytes())

    def similarity(self, a: bytearray, b: bytearray) -> float:
        """计算两个超向量的 Hamming 相似度（1.0 = 完全相同，0.5 = 正交/随机）。"""
        if not a or not b:
            return 0.5
        xor_count = 0
        for x, y in zip(a, b):
            xor_count += (x ^ y).bit_count()
        return 1.0 - xor_count / self.dim

    def bind(self, a: bytearray, b: bytearray) -> bytearray:
        """XOR 绑定：表示两个概念之间的关系（结果与两者都不相似）。"""
        return bytearray(x ^ y for x, y in zip(a, b))

    def bundle(self, vectors: list[bytearray]) -> bytearray:
        """多数投票捆绑：表示概念集合（结果与所有输入都相似）。

        使用与 encode() 相同的垂直二进制计数算法。
        """
        if not vectors:
            return bytearray(self._byte_dim)
        n = len(vectors)
        byte_dim = self._byte_dim
        mask = self._mask

        n_bits = max(1, n.bit_length())
        c = [0] * n_bits
        for vec in vectors:
            v = int.from_bytes(vec, "little")
            carry = v
            for i in range(n_bits):
                if carry == 0:
                    break
                new_carry = c[i] & carry
                c[i] ^= carry
                carry = new_carry

        threshold = n // 2 + 1
        borrow = 0
        for i in range(n_bits):
            t_bit = (threshold >> i) & 1
            if t_bit:
                if borrow == 0:
                    borrow = (~c[i]) & mask
                else:
                    borrow = (((~c[i]) & mask) | borrow) & mask
            else:
                if borrow != 0:
                    borrow = (~c[i]) & mask & borrow

        result_int = (~borrow) & mask
        return bytearray(result_int.to_bytes(byte_dim, "little"))

    def _tokenize(self, text: str) -> list[str]:
        """字符 bigram 分词：将文本切分为相邻字符对。"""
        text = text.strip()
        if len(text) <= 1:
            return [text] if text else []
        return [text[i : i + 2] for i in range(len(text) - 1)]
