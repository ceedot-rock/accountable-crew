#!/usr/bin/env python3
"""near_intents.py — the crew's NEAR testnet payment leg.

NEAR technologies used (testnet only):
- NEAR Intents: the agent payment leg is expressed as an intent
  (a signed `token_diff` declaration of what goes in / what is
  expected out), to be filled by a solver. This module BUILDS the
  intent object and gates it against the Warrant mandate. It does NOT
  fetch a solver quote, does NOT sign, and does NOT broadcast.
- Chain Signatures: an agent signs for other chains without holding
  keys by asking the NEAR MPC contract to sign a 32-byte payload hash
  under a derivation path. This module builds that sign REQUEST
  (contract, method, args) and derives the path. It does NOT call the
  contract — no MPC contract is configured on this machine, and no
  funded NEAR key exists here.

Honesty contract (same pattern as mandate-gate/paid_call.py):
- No key / no MPC contract configured -> NearNotConfigured carrying
  exactly what would have been asked, never a silent fake.
- The mandate gate runs BEFORE any intent is built into an executable
  request. A denied intent is returned with executed=False and no
  signature request is ever built for it.
- `check_testnet_status()` is the only live-network call: a read-only
  JSON-RPC `status` query against the public testnet RPC. It never
  raises; unreachable network becomes {"reachable": False, ...}.
- Status at build (2026-11-14): TESTNET DRY-RUN ONLY. No intent has
  been quoted, signed, or settled on any chain. The submission form
  must say testnet-only.

Stdlib only — no third-party packages, so the leg runs anywhere the
rest of the crew runs.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.request
import urllib.error

TESTNET_RPC_URL = "https://rpc.testnet.near.org"
NETWORK = "testnet"

# NEAR implicit accounts are the 64-hex public key itself. Corey's
# payout account (supplied 2026-11-14) is one of these; the same id
# names the account on testnet and mainnet.
_ACCOUNT_RE = re.compile(r"^[a-z0-9._-]{2,64}$")
_IMPLICIT_RE = re.compile(r"^[0-9a-f]{64}$")


class NearError(RuntimeError):
    """The NEAR leg could not do what was asked; str(self) says why."""


class NearNotConfigured(NearError):
    """No MPC contract / signing route configured. Carries the exact
    sign request that was NOT sent, so the caller can receipt it."""

    def __init__(self, request: dict):
        self.request = request
        super().__init__(
            "no MPC contract configured (NEAR_MPC_CONTRACT unset): "
            "chain-signature request built, NOT sent"
        )


def is_valid_account_id(account_id: str) -> bool:
    """A NEAR account id: 2-64 chars, lowercase alnum plus . _ -,
    or a 64-hex implicit account."""
    if not isinstance(account_id, str):
        return False
    return bool(_ACCOUNT_RE.match(account_id) or _IMPLICIT_RE.match(account_id))


def build_intent(signer_id: str, asset_in: str, asset_out: str,
                 amount_in: int, deadline_ms: int | None = None,
                 nonce: str | None = None,
                 min_amount_out: int | None = None) -> dict:
    """Build a NEAR Intents swap declaration (dry-run object only).

    asset_in / asset_out are NEAR asset ids as the caller supplies
    them (e.g. "wrap.testnet"). amount_in is raw base units of
    asset_in and must be a positive int. deadline_ms is an epoch-ms
    deadline; default is now + 5 minutes. No quote is fetched, so
    there is no guaranteed out-amount: min_amount_out, if given, is
    the caller's floor, recorded in the intent for the solver.
    Returns the intent dict with network/execution markers attached.
    """
    if not is_valid_account_id(signer_id):
        raise NearError(f"invalid NEAR signer account id: {signer_id!r}")
    for name, asset in (("asset_in", asset_in), ("asset_out", asset_out)):
        if not isinstance(asset, str) or not asset:
            raise NearError(f"{name} must be a non-empty asset id")
    if not isinstance(amount_in, int) or isinstance(amount_in, bool) \
            or amount_in <= 0:
        raise NearError(f"amount_in must be a positive int, got {amount_in!r}")
    now_ms = int(time.time() * 1000)
    deadline = deadline_ms if deadline_ms is not None else now_ms + 300_000
    if not isinstance(deadline, int) or deadline <= now_ms:
        raise NearError("deadline_ms must be an epoch-ms time in the future")
    diff = {asset_in: f"-{amount_in}"}
    token_diff = {"intent": "token_diff", "diff": diff}
    if min_amount_out is not None:
        if not isinstance(min_amount_out, int) or min_amount_out <= 0:
            raise NearError("min_amount_out must be a positive int")
        token_diff["diff"][asset_out] = f"+{min_amount_out}"
    intent = {
        "network": NETWORK,
        "signer_id": signer_id,
        "deadline": deadline,
        "nonce": nonce or hashlib.sha256(
            f"{signer_id}:{asset_in}:{asset_out}:{amount_in}:{deadline}"
            .encode()).hexdigest()[:16],
        "intents": [token_diff],
        "execution": "NOT_EXECUTED",
        "status": "dry-run",
    }
    return intent


def intent_payload_hash(intent: dict) -> bytes:
    """The 32-byte payload a Chain Signatures MPC call would sign:
    SHA-256 of the canonical intent JSON. Deterministic: same intent
    in, same hash out."""
    canon = json.dumps(intent, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).digest()


def chain_signature_derivation_path(account_index: int = 0,
                                    chain_index: int = 0,
                                    address_index: int = 1) -> str:
    """Derivation path for a Chain Signatures MPC sign call.

    NEAR Chain Signatures derivation paths are BIP-44-style strings
    under coin type 397 (NEAR): 44'/397'/<account>'/<chain>'/<address>'.
    All indices must be non-negative ints.
    """
    for name, v in (("account_index", account_index),
                    ("chain_index", chain_index),
                    ("address_index", address_index)):
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise NearError(f"{name} must be a non-negative int, got {v!r}")
    return (f"44'/397'/{account_index}'/{chain_index}'/"
            f"{address_index}'")


def chain_signature_request(intent: dict, derivation_path: str,
                            mpc_contract: str | None = None,
                            key_version: int = 0) -> dict:
    """Build the MPC `sign` contract-call args for an intent's hash.

    Without mpc_contract: raises NearNotConfigured carrying the exact
    request that was NOT sent. With one: returns the call dict
    (contract, method "sign", args {payload: [32 bytes as ints],
    path, key_version}) — the caller still has to submit it; this
    module never submits anything.
    """
    payload = list(intent_payload_hash(intent))
    request = {
        "contract": mpc_contract,
        "method": "sign",
        "args": {"payload": payload, "path": derivation_path,
                 "key_version": key_version},
        "network": NETWORK,
    }
    if not mpc_contract:
        raise NearNotConfigured(request)
    if not is_valid_account_id(mpc_contract):
        raise NearError(f"invalid MPC contract account id: {mpc_contract!r}")
    return request


def check_testnet_status(timeout: int = 30, opener=None) -> dict:
    """Read-only liveness probe of the NEAR testnet RPC (JSON-RPC
    `status`). Never raises: failure is a result, not a crash.
    Default timeout is 30s: the VM's egress proxy is slow and a 10s
    timeout timed out on a live endpoint (2026-11-14).

    `opener` is an injectable (url, body, timeout) -> response hook
    for tests; default is a real urllib POST to TESTNET_RPC_URL.
    """
    def _real(url: str, body: bytes, timeout_s: int):
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"})
        return urllib.request.urlopen(req, timeout=timeout_s)

    call = opener or _real
    body = json.dumps({"jsonrpc": "2.0", "id": "crew-near-status",
                       "method": "status", "params": []}).encode()
    try:
        with call(TESTNET_RPC_URL, body, timeout) as resp:
            out = json.loads(resp.read().decode())
    except Exception as e:  # network down, DNS, timeout — a result
        return {"reachable": False, "rpc_url": TESTNET_RPC_URL,
                "network": NETWORK, "error": f"{type(e).__name__}: {e}"}
    result = out.get("result") or {}
    return {
        "reachable": True,
        "rpc_url": TESTNET_RPC_URL,
        "network": NETWORK,
        "chain_id": result.get("chain_id"),
        "latest_block_height": (result.get("sync_info") or {})
        .get("latest_block_height"),
        "latest_block_hash": (result.get("sync_info") or {})
        .get("latest_block_hash"),
    }


def gate_intent(ledger, warrant: dict, caller_agent_id: str,
                cost_cents: int, intent: dict,
                now: int | None = None) -> dict:
    """Mandate-gate an intent BEFORE it becomes an executable request.

    Runs the ledger's gate_payment first. ALLOW -> the intent is
    returned with executed=False and an explicit dry-run marker (no
    quote, no signature, no broadcast happened). DENY -> the gate
    decision is returned verbatim with the intent attached and
    executed=False; no signature request is built for a denied intent.
    """
    decision = ledger.gate_payment(warrant, caller_agent_id, cost_cents,
                                   now=now)
    record = {
        "intent": intent,
        "executed": False,
        "gate": decision,
    }
    if decision["ok"]:
        record["execution"] = ("dry-run only — quote/signature/broadcast "
                               "not performed")
        record["remaining_cents"] = decision.get("remaining_cents")
    else:
        record["execution"] = "BLOCKED by mandate gate — nothing sent"
    return record


if __name__ == "__main__":
    raise SystemExit("library — see README.md; run the demo via "
                     "near-rail/demo_testnet.py")
