"""Sylanne-Embodiment computation layer: Hyperdimensional Computing encoder.

Encodes text into sparse binary hypervectors for ultra-fast
similarity matching and compositional representation.
Uses bytearray for compact storage and fast bitwise operations.

Performance: vertical binary counting with Python big-ints and
pre-computed bit-masks for the per-byte shift operation, eliminating
all inner Python loops during encoding.
"""

from __future__ import annotations

import hashlib
import struct
from collections import OrderedDict

_SEED_CACHE_MAXSIZE = 10000
_SEED_CACHE_EVICT_COUNT = 1000


def _build_shift_masks(byte_dim: int, dim: int) -> tuple:
    """Pre-compute masks for each sub-byte shift remainder (1-7).

    For shift_remainder r, the per-byte operation is:
      output[B] = (rot[B] >> r) | ((rot[B-1] & low_r_mask) << (8-r))

    This decomposes into two masked global int operations:
      part1 = (rot_int >> r) & keep_mask   (bits 0..7-r of each byte)
      part2 = circular_left_shift(rot_int & low_mask, 16-r) & high_mask
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
    __slots__ = ("dim", "_byte_dim", "_seed_cache", "_mask", "_shift_masks")

    def __init__(self, dim: int = 1024):
        self.dim = dim
        self._byte_dim = dim // 8
        self._seed_cache: OrderedDict[str, bytearray] = OrderedDict()
        self._mask = (1 << dim) - 1
        self._shift_masks = _build_shift_masks(self._byte_dim, dim)

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
        """Encode token sequence into a single hypervector via shift+bundle.

        Uses vertical binary counting with Python big-ints: each counter
        bit-plane is a single dim-bit int, so the per-token addition is
        O(log n) big-int AND/XOR ops instead of O(dim) scalar increments.
        The shift uses pre-computed masks for O(1) big-int ops per token.
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
        """Majority-vote bundling using vertical binary counting."""
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
        """Character bigram tokenization."""
        text = text.strip()
        if len(text) <= 1:
            return [text] if text else []
        return [text[i : i + 2] for i in range(len(text) - 1)]
