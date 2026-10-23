#!/usr/bin/env python3
"""ethsig.py — minimal Ethereum signing primitives, pure Python.

Why this exists: this VM has no eth_account / web3 / coincurve /
pycryptodome (checked 2026-10-22), and the x402 payment leg needs
Keccak-256, secp256k1 signing with recovery id, and EIP-191
personal_sign. Everything here is small, standard, and pinned by
known-answer tests in ../tests/test_ethsig.py:

- Keccak-256: original Keccak padding (0x01), NOT NIST SHA3-256.
- secp256k1: plain affine EC math (slow, fine for occasional signing).
- RFC 6979 deterministic nonces (HMAC-SHA256), low-s normalized.

This is client-side signing for the crew's own payer key only. It is
not a general wallet and holds no keys itself.
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod

# ---------------------------------------------------------------------------
# Keccak-256 (Keccak-f[1600], rate 1088, capacity 512, pad10*1 domain 0x01)
# ---------------------------------------------------------------------------

_MASK64 = (1 << 64) - 1

_KECCAK_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A,
    0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
    0x8000000080008081, 0x8000000000008009, 0x000000000000008A,
    0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
    0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
    0x000000000000800A, 0x800000008000000A, 0x8000000080008081,
    0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]

_KECCAK_ROT = [
    [0, 36, 3, 41, 18],
    [1, 44, 10, 45, 2],
    [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56],
    [27, 20, 39, 8, 14],
]

def _rotl64(x: int, n: int) -> int:
    return ((x << n) | (x >> (64 - n))) & _MASK64 if n else x


def _keccak_f1600(state: list) -> None:
    # Lanes are indexed state[x + 5*y] for coordinates (x, y), per spec.
    for rc in _KECCAK_RC:
        # theta: C[x] = column parity; D[x] = C[x-1] ^ rot(C[x+1], 1)
        c = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20]
             for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rotl64(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] ^= d[x]
        # rho + pi combined: B[x][y] = rot(A[(x+3y) mod 5][x],
        # r[(x+3y) mod 5][x]) — rotation is indexed by the SOURCE lane's
        # own coordinates, per the spec's separate rho and pi steps.
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                sx, sy = (x + 3 * y) % 5, x
                b[x + 5 * y] = _rotl64(state[sx + 5 * sy], _KECCAK_ROT[sx][sy])
        # chi: A[x][y] = B[x][y] ^ (~B[x+1][y] & B[x+2][y])
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] = (b[x + 5 * y]
                                    ^ ((~b[(x + 1) % 5 + 5 * y]) & b[(x + 2) % 5 + 5 * y])) & _MASK64
        # iota
        state[0] ^= rc


def keccak256(data: bytes) -> bytes:
    rate = 136  # bytes, for 256-bit output
    state = [0] * 25
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % rate != rate - 1:
        padded.append(0x00)
    padded.append(0x80)
    for off in range(0, len(padded), rate):
        block = padded[off:off + rate]
        for i in range(rate // 8):
            state[i] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
        _keccak_f1600(state)
    out = bytearray()
    for i in range(4):
        out += state[i].to_bytes(8, "little")
    return bytes(out[:32])


# ---------------------------------------------------------------------------
# secp256k1
# ---------------------------------------------------------------------------

_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_G = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)


def _ec_add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % _P == 0:
        return None
    if p1 == p2:
        m = (3 * x1 * x1) * pow(2 * y1, -1, _P) % _P
    else:
        m = (y2 - y1) * pow(x2 - x1, -1, _P) % _P
    x3 = (m * m - x1 - x2) % _P
    y3 = (m * (x1 - x3) - y1) % _P
    return (x3, y3)


def _ec_mul(k: int, point):
    result = None
    addend = point
    while k:
        if k & 1:
            result = _ec_add(result, addend)
        addend = _ec_add(addend, addend)
        k >>= 1
    return result


def privkey_to_pubkey(priv: int) -> tuple:
    return _ec_mul(priv, _G)


def pubkey_to_address(pub: tuple) -> str:
    x, y = pub
    digest = keccak256(x.to_bytes(32, "big") + y.to_bytes(32, "big"))
    return "0x" + digest[-20:].hex()


def privkey_to_address(priv: int) -> str:
    return pubkey_to_address(privkey_to_pubkey(priv))


def _rfc6979_nonce(priv: int, digest: bytes) -> int:
    bx = priv.to_bytes(32, "big")
    bh = (int.from_bytes(digest, "big") % _N).to_bytes(32, "big")
    v = b"\x01" * 32
    k = b"\x00" * 32
    k = hmac_mod.new(k, v + b"\x00" + bx + bh, hashlib.sha256).digest()
    v = hmac_mod.new(k, v, hashlib.sha256).digest()
    k = hmac_mod.new(k, v + b"\x01" + bx + bh, hashlib.sha256).digest()
    v = hmac_mod.new(k, v, hashlib.sha256).digest()
    while True:
        v = hmac_mod.new(k, v, hashlib.sha256).digest()
        candidate = int.from_bytes(v, "big")
        if 1 <= candidate < _N:
            return candidate
        k = hmac_mod.new(k, v + b"\x00", hashlib.sha256).digest()
        v = hmac_mod.new(k, v, hashlib.sha256).digest()


def sign_digest(priv: int, digest: bytes) -> tuple:
    """ECDSA-sign a 32-byte digest. Returns (v, r, s) with v in {27, 28},
    low-s normalized, RFC 6979 deterministic."""
    if len(digest) != 32:
        raise ValueError("digest must be 32 bytes")
    z = int.from_bytes(digest, "big")
    k = _rfc6979_nonce(priv, digest)
    rx, ry = _ec_mul(k, _G)
    r = rx % _N
    s = (pow(k, -1, _N) * (z + r * priv)) % _N
    recid = (ry & 1) | (2 if rx >= _N else 0)
    if s > _N // 2:
        s = _N - s
        recid ^= 1
    return (27 + recid, r, s)


def recover_address(digest: bytes, v: int, r: int, s: int) -> str:
    recid = v - 27
    x = r + (recid >> 1) * _N
    if x >= _P:
        raise ValueError("recovery x out of range")
    y_sq = (pow(x, 3, _P) + 7) % _P
    y = pow(y_sq, (_P + 1) // 4, _P)
    if (y & 1) != (recid & 1):
        y = _P - y
    point_r = (x, y)
    z = int.from_bytes(digest, "big")
    r_inv = pow(r, -1, _N)
    q = _ec_mul(r_inv, _ec_add(_ec_mul(s, point_r), _ec_mul((-z) % _N, _G)))
    return pubkey_to_address(q)


# ---------------------------------------------------------------------------
# EIP-191 personal_sign
# ---------------------------------------------------------------------------

def eip191_hash(message: bytes) -> bytes:
    prefix = b"\x19Ethereum Signed Message:\n" + str(len(message)).encode()
    return keccak256(prefix + message)


def personal_sign(priv: int, message: bytes) -> str:
    """Sign `message` per EIP-191; return 0x-prefixed 65-byte hex signature."""
    v, r, s = sign_digest(priv, eip191_hash(message))
    sig = r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([v])
    return "0x" + sig.hex()


def parse_privkey(key_hex: str) -> int:
    h = key_hex.strip()
    if h.startswith("0x"):
        h = h[2:]
    priv = int(h, 16)
    if not (1 <= priv < _N):
        raise ValueError("private key out of range")
    return priv
