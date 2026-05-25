"""Sylanne-Embodiment computation layer: Hyperdimensional Computing encoder.

Encodes text into sparse binary hypervectors for ultra-fast
similarity matching and compositional representation.
Uses bytearray for compact storage and fast bitwise operations.
"""

from __future__ import annotations

import hashlib
import struct
from collections import OrderedDict

_SEED_CACHE_MAXSIZE = 10000
_SEED_CACHE_EVICT_COUNT = 1000


class HDCEncoder:
    __slots__ = ("dim", "_byte_dim", "_seed_cache")

    def __init__(self, dim: int = 1024):
        self.dim = dim
        self._byte_dim = dim // 8
        self._seed_cache: OrderedDict[str, bytearray] = OrderedDict()

    def atom(self, token: str) -> bytearray:
        """Deterministic random binary vector for a token (packed bytes)."""
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
        """Encode token sequence into a single hypervector via shift+bundle."""
        if not tokens:
            return bytearray(self._byte_dim)
        n = len(tokens)
        # Accumulate bit counts
        counts = [0] * self.dim
        for pos, token in enumerate(tokens):
            a = self.atom(token)
            shift_bits = pos % self.dim
            shift_bytes = shift_bits // 8
            shift_remainder = shift_bits % 8
            for byte_idx in range(self._byte_dim):
                src_idx = (byte_idx - shift_bytes) % self._byte_dim
                byte_val = a[src_idx]
                if shift_remainder == 0:
                    for bit in range(8):
                        if byte_val & (1 << bit):
                            counts[byte_idx * 8 + bit] += 1
                else:
                    src_idx2 = (src_idx - 1) % self._byte_dim
                    combined = ((a[src_idx2] << 8) | byte_val) >> shift_remainder
                    for bit in range(8):
                        if combined & (1 << bit):
                            counts[byte_idx * 8 + bit] += 1
        # Majority vote
        threshold = n / 2.0
        result = bytearray(self._byte_dim)
        for i in range(self.dim):
            if counts[i] > threshold:
                result[i // 8] |= 1 << (i % 8)
        return result

    def encode_text(self, text: str) -> bytearray:
        """Encode raw text (character-level bigrams as tokens)."""
        if not text:
            return bytearray(self._byte_dim)
        tokens = self._tokenize(text)
        return self.encode(tokens)

    def similarity(self, a: bytearray, b: bytearray) -> float:
        """Hamming similarity using popcount on XOR."""
        if not a or not b:
            return 0.5
        xor_count = 0
        for x, y in zip(a, b):
            xor_count += bin(x ^ y).count("1")
        return 1.0 - xor_count / self.dim

    def bind(self, a: bytearray, b: bytearray) -> bytearray:
        """XOR binding."""
        return bytearray(x ^ y for x, y in zip(a, b))

    def bundle(self, vectors: list[bytearray]) -> bytearray:
        """Majority-vote bundling."""
        if not vectors:
            return bytearray(self._byte_dim)
        n = len(vectors)
        counts = [0] * self.dim
        for vec in vectors:
            for byte_idx in range(self._byte_dim):
                byte_val = vec[byte_idx]
                for bit in range(8):
                    if byte_val & (1 << bit):
                        counts[byte_idx * 8 + bit] += 1
        threshold = n / 2.0
        result = bytearray(self._byte_dim)
        for i in range(self.dim):
            if counts[i] > threshold:
                result[i // 8] |= 1 << (i % 8)
        return result

    def _tokenize(self, text: str) -> list[str]:
        """Character bigram tokenization."""
        text = text.strip()
        if len(text) <= 1:
            return [text] if text else []
        return [text[i : i + 2] for i in range(len(text) - 1)]
