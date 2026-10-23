#!/usr/bin/env python3
"""paid_call.py — x402 (txHash scheme) paid HTTP calls for the crew.

Implements the client side of the handshake documented in
~/workspace/custom-skills/x402-api-client/SKILL.md against the live
rail at rider-x402.fly.dev:

  1. POST without payment -> 402 with machine-readable terms (network,
     amount in base units, USDC contract, payTo, and a `howto` text).
  2. Pay >= the stated amount of USDC to payTo on that network
     (a plain ERC-20 transfer, signed locally via ethsig.py).
  3. Sign the server's binding message with the paying key (EIP-191):
     "rider-x402 payment proof\\ntxHash: <lowercase hash>\\nresource:
     <resource URL>" — the exact string the server reconstructs and
     verifies (rider-x402/ethsig.py binding_message). The 402's
     extra.howto is the human-readable description of this, with the
     tx hash left as a placeholder; it is never signed verbatim.
  4. Retry the same request with X-PAYMENT: base64url (no padding) of
     {"x402Version":2,"scheme":"txHash","network":..., "payload":
     {"txHash": ..., "payerSig": ...}}.

Rules honored from the skill: terms are read fresh from the 402 on
every call (never cached), one payment pays for exactly one call, and
no payment is attempted without a configured payer key — callers get
PaidCallNotFunded carrying the live terms instead of a silent skip.
The mandate gate (gate.py) always runs BEFORE this module is asked to
pay; this module never decides whether a spend is allowed.
"""

from __future__ import annotations

import base64
import json
import time

import requests

import ethsig

X402_BASE = "https://rider-x402.fly.dev"
PCC_INFO_URL = X402_BASE + "/api/x402/pcc/info"
PCC_COMPRESS_URL = X402_BASE + "/api/x402/pcc/compress"
PCC_DECOMPRESS_URL = X402_BASE + "/api/x402/pcc/decompress"

_NETWORKS = {
    "base": {"chain_id": 8453, "rpc": "https://mainnet.base.org"},
    "eip155:8453": {"chain_id": 8453, "rpc": "https://mainnet.base.org"},
    "polygon": {"chain_id": 137, "rpc": "https://polygon-rpc.com"},
    "eip155:137": {"chain_id": 137, "rpc": "https://polygon-rpc.com"},
}


class PaidCallError(RuntimeError):
    """The paid call could not be completed; str(self) says why."""


class PaidCallNotFunded(PaidCallError):
    """No payer key configured. Carries the live 402 terms so the
    caller can receipt exactly what was asked and not paid."""

    def __init__(self, terms: dict):
        self.terms = terms
        super().__init__(
            "no payer key configured (CREW_X402_PAYER_KEY unset): "
            "402 terms captured, payment NOT executed"
        )


# ---------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------

def _post(url: str, body_obj: dict, headers: dict | None = None,
          timeout: int = 30) -> requests.Response:
    return requests.post(url, json=body_obj, headers=headers or {},
                         timeout=timeout)


def fetch_terms(url: str, body_obj: dict, timeout: int = 30) -> dict:
    """POST unpaid; return the normalized 402 terms (raw body kept)."""
    r = _post(url, body_obj, timeout=timeout)
    if r.status_code != 402:
        raise PaidCallError(
            f"expected 402 from {url}, got {r.status_code}: {r.text[:200]}")
    try:
        body = r.json()
    except ValueError:
        raise PaidCallError(f"402 from {url} was not JSON: {r.text[:200]}")
    options = body.get("accepts") or [body]
    chosen = next((o for o in options if o.get("scheme") == "txHash"),
                  options[0])
    amount_raw = chosen.get("maxAmountRequired") or chosen.get("amount")
    howto = (chosen.get("howto")
             or (chosen.get("extra") or {}).get("howto")
             or body.get("howto"))
    terms = {
        "url": url,
        "network": chosen.get("network") or body.get("network"),
        "scheme": chosen.get("scheme") or body.get("scheme"),
        "amount_base_units": int(amount_raw) if amount_raw is not None else None,
        "asset": chosen.get("asset"),
        "pay_to": chosen.get("payTo") or chosen.get("pay_to"),
        "resource": chosen.get("resource") or url,
        "howto": howto,
        "raw": body,
    }
    return terms


def binding_message(tx_hash: str, resource: str) -> bytes:
    """The exact bytes the payer signs — mirrors the server's
    rider-x402/ethsig.py binding_message, character for character."""
    return ("rider-x402 payment proof\n"
            "txHash: %s\n"
            "resource: %s" % (tx_hash.strip().lower(),
                              resource.strip())).encode()


def terms_price_cents(terms: dict) -> int:
    """USDC has 6 decimals: 1 cent = 10_000 base units, exactly."""
    amt = terms.get("amount_base_units")
    if amt is None or amt % 10_000 != 0:
        raise PaidCallError(f"terms amount {amt!r} is not a whole-cent "
                            "number of USDC base units")
    return amt // 10_000


# ---------------------------------------------------------------------------
# On-chain payment (ERC-20 transfer) via public RPC
# ---------------------------------------------------------------------------

def _rlp_encode(item) -> bytes:
    if isinstance(item, int):
        if item == 0:
            return _rlp_encode(b"")
        raw = item.to_bytes((item.bit_length() + 7) // 8, "big")
        return _rlp_encode(raw)
    if isinstance(item, (bytes, bytearray)):
        data = bytes(item)
        if len(data) == 1 and data[0] < 0x80:
            return data
        if len(data) <= 55:
            return bytes([0x80 + len(data)]) + data
        lb = len(data).to_bytes((len(data).bit_length() + 7) // 8, "big")
        return bytes([0xB7 + len(lb)]) + lb + data
    if isinstance(item, (list, tuple)):
        payload = b"".join(_rlp_encode(x) for x in item)
        if len(payload) <= 55:
            return bytes([0xC0 + len(payload)]) + payload
        lb = len(payload).to_bytes((len(payload).bit_length() + 7) // 8, "big")
        return bytes([0xF7 + len(lb)]) + lb + payload
    raise TypeError(f"cannot RLP-encode {type(item)}")


def _rpc(rpc_url: str, method: str, params: list, timeout: int = 30):
    r = requests.post(rpc_url, json={"jsonrpc": "2.0", "id": 1,
                                     "method": method, "params": params},
                      timeout=timeout)
    out = r.json()
    if "error" in out:
        raise PaidCallError(f"RPC {method} failed: {out['error']}")
    return out["result"]


def _send_usdc_transfer(rpc_url: str, chain_id: int, priv: int,
                        token: str, to_addr: str, amount: int,
                        timeout: int = 30) -> str:
    """Broadcast one ERC-20 transfer; return the tx hash once mined."""
    payer = ethsig.privkey_to_address(priv)
    selector = ethsig.keccak256(b"transfer(address,uint256)")[:4]
    data = (selector
            + bytes.fromhex(to_addr[2:].rjust(64, "0"))
            + amount.to_bytes(32, "big"))
    nonce = int(_rpc(rpc_url, "eth_getTransactionCount",
                     [payer, "pending"], timeout), 16)
    gas_price = int(_rpc(rpc_url, "eth_gasPrice", [], timeout), 16)
    try:
        gas = int(_rpc(rpc_url, "eth_estimateGas",
                       [{"from": payer, "to": token,
                         "data": "0x" + data.hex()}], timeout), 16)
        gas = int(gas * 1.2) + 5000
    except PaidCallError:
        gas = 120_000
    tx_fields = [nonce, gas_price, gas, bytes.fromhex(token[2:]), 0, data,
                 chain_id, 0, 0]  # EIP-155 signing form
    signing_hash = ethsig.keccak256(_rlp_encode(tx_fields))
    v, r_, s = ethsig.sign_digest(priv, signing_hash)
    v = chain_id * 2 + 35 + (v - 27)
    signed = _rlp_encode([nonce, gas_price, gas, bytes.fromhex(token[2:]),
                          0, data, v, r_, s])
    tx_hash = _rpc(rpc_url, "eth_sendRawTransaction",
                   ["0x" + signed.hex()], timeout)
    deadline = time.time() + 120
    while time.time() < deadline:
        receipt = _rpc(rpc_url, "eth_getTransactionReceipt", [tx_hash],
                       timeout)
        if receipt:
            if receipt.get("status") != "0x1":
                raise PaidCallError(f"USDC transfer {tx_hash} reverted")
            return tx_hash
        time.sleep(3)
    raise PaidCallError(f"USDC transfer {tx_hash} not mined within 120s")


# ---------------------------------------------------------------------------
# The paid call
# ---------------------------------------------------------------------------

def execute_paid_call(url: str, body_obj: dict, payer_privkey_hex: str,
                      terms: dict | None = None,
                      timeout: int = 30) -> dict:
    """Pay the 402 terms on-chain and retry with the X-PAYMENT proof."""
    terms = terms or fetch_terms(url, body_obj, timeout=timeout)
    net = _NETWORKS.get(str(terms.get("network")))
    if net is None:
        raise PaidCallError(f"unsupported x402 network: {terms.get('network')!r}")
    if not terms.get("asset") or not terms.get("pay_to"):
        raise PaidCallError("402 terms missing asset or payTo")
    priv = ethsig.parse_privkey(payer_privkey_hex)
    tx_hash = _send_usdc_transfer(net["rpc"], net["chain_id"], priv,
                                  terms["asset"], terms["pay_to"],
                                  terms["amount_base_units"], timeout)
    payer_sig = ethsig.personal_sign(
        priv, binding_message(tx_hash, terms["resource"]))
    proof = {
        "x402Version": 2,
        "scheme": "txHash",
        "network": terms["network"],
        "payload": {"txHash": tx_hash, "payerSig": payer_sig},
    }
    header = base64.urlsafe_b64encode(
        json.dumps(proof, separators=(",", ":")).encode()
    ).decode().rstrip("=").replace("+", "-").replace("/", "_")
    r = _post(url, body_obj, headers={"X-PAYMENT": header}, timeout=timeout)
    try:
        payload = r.json()
    except ValueError:
        payload = {"raw": r.text[:500]}
    return {"status": r.status_code, "tx_hash": tx_hash,
            "payer": ethsig.privkey_to_address(priv),
            "terms": terms, "response": payload}


def paid_call(url: str, body_obj: dict, payer_privkey_hex: str | None,
              timeout: int = 30) -> dict:
    """Gate-friendly entry point: no key -> PaidCallNotFunded (with the
    live terms attached); key -> execute_paid_call."""
    terms = fetch_terms(url, body_obj, timeout=timeout)
    if not payer_privkey_hex:
        raise PaidCallNotFunded(terms)
    return execute_paid_call(url, body_obj, payer_privkey_hex,
                             terms=terms, timeout=timeout)


if __name__ == "__main__":
    raise SystemExit("library — see README.md")
