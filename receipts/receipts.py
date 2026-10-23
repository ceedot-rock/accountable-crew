#!/usr/bin/env python3
"""receipts.py — CuNi envelope emission + verification for crew actions.

Wraps the verified implementation at
~/workspace/fabric-phase1/builds/receipts/cuni_envelope.py
(assemble_envelope / verify_envelope; corpus 20/20, milestone 12/12,
run 2026-10-22). Receipts are append-only JSONL on local disk; the
console reads the same file for the timeline view.

Crew conventions (decided 2026-10-22, this build):

- receipt_kind is "check", not the scaffold's "audit" default. In
  cuni_envelope, "audit" semantics demand code-audit artifacts
  (law_sha256 / impl_sha256 recomputation over audited source). Crew
  action records are check-kind: an action happened, a named signer
  attests to the record, and the envelope binds it. _semantics_check
  enforces exactly that (signature valid, verdict a non-empty string).
- Every action record is *inner-signed* by the acting seat's own
  Ed25519 key (assemble_envelope refuses unsigned inner receipts):
  sign_action() adds signer_pubkey + signature over the canonical bytes
  cuni_envelope itself defines. The trail issuer key signs the outer
  envelope. Two different keys, two different claims — the seat attests
  "I did this", the issuer attests "this record is in the trail".
- These seat Ed25519 keys are LOCAL action-signing keys (files under
  ../.keys/, 0600). They are not Rider identities; Rider identity is
  the ES256 JWT layer. The receipt binds the seat's Rider agent_id in
  the record body so the two layers can be cross-checked.
- No floats anywhere in a record: cuni canonical bytes reject them.
  _canon_safe() coerces integral floats to int and anything else
  non-canonical to str, at record time — never silently at verify time.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / "workspace" / "fabric-phase1" /
                    "builds" / "receipts"))
from cuni_envelope import (  # noqa: E402
    EnvelopeError,
    VerifyFailure,
    assemble_envelope,
    gen_keypair,
    load_key_file,
    pubkey_of,
    sign_bytes,
    tool_canonical_bytes,
    verify_envelope,
)

RECEIPT_KIND = "check"
TRAIL_PATH = Path(__file__).with_name("trail.jsonl")
KEYS_DIR = Path(__file__).resolve().parent.parent / ".keys"

# Envelope meta the crew can state truthfully for every action receipt.
DEFAULT_TARGET = {
    "repo": "slid-phi-labs/accountable-crew (local build, unpublished)",
    "commit": "none — local working tree, 2026-10-22",
    "scope_files": ["agent-loop/", "mandate-gate/", "receipts/"],
    "out_of_scope": ["Agent-Rider server (live; accessed via MCP only)"],
    "impl_extraction": "crew action records emitted at runtime by receipts.py",
}
DEFAULT_PROPERTY = (
    "Accountability: every cross-agent action in this trail was performed "
    "by a named Agent-Rider seat, checked against a Warrant spend mandate "
    "before any spend, and is tamper-evident after the fact."
)
DEFAULT_PROPERTY_REF = {
    "law_file": "open-agent-hackathon-build-plan.md — five Day-1 answers, answer 4",
    "impl_file": "fabric-phase1/builds/receipts/cuni_envelope.py",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canon_safe(obj):
    """Coerce a record into cuni-canonical-safe shapes (no floats)."""
    if isinstance(obj, float):
        return int(obj) if obj.is_integer() else str(obj)
    if isinstance(obj, dict):
        return {str(k): _canon_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_canon_safe(v) for v in obj]
    if isinstance(obj, (str, int, bool)) or obj is None:
        return obj
    return str(obj)


def sign_action(action: dict, signer_priv: bytes) -> dict:
    """Inner-sign one action record with the acting seat's Ed25519 key.

    Field order is part of the signature for check-kind receipts
    (insertion-order canonicalization), so the record is built, then
    signer_pubkey is appended, then signature is appended last — the
    exact layout verify_envelope recomputes.
    """
    inner = _canon_safe(dict(action))
    inner["signer_pubkey"] = pubkey_of(signer_priv)
    inner["signature"] = sign_bytes(
        signer_priv,
        tool_canonical_bytes(inner, RECEIPT_KIND, include_signature=False),
    )
    return inner


def ensure_keypair(keys_dir: Path, name: str) -> tuple[bytes, str]:
    """Load `<name>.key` (32 raw bytes, 0600) + `<name>.pub` (hex) from
    keys_dir, generating the pair on first use. Refuses to overwrite."""
    keys_dir.mkdir(parents=True, exist_ok=True)
    key_path = keys_dir / f"{name}.key"
    pub_path = keys_dir / f"{name}.pub"
    if key_path.exists():
        priv = load_key_file(str(key_path))
        return priv, pubkey_of(priv)
    priv, pub_hex = gen_keypair()
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(priv)
    with open(pub_path, "w") as f:
        f.write(pub_hex + "\n")
    return priv, pub_hex


class CrewTrail:
    """One run's receipt trail: an issuer key + an append-only JSONL file."""

    def __init__(
        self,
        trail_path: Path | str,
        issuer_priv: bytes,
        key_id: str,
        audit_id: str,
        issuer_did: str,
        target: dict | None = None,
        property_text: str = DEFAULT_PROPERTY,
        property_ref: dict | None = None,
    ):
        self.trail_path = Path(trail_path)
        self.trail_path.parent.mkdir(parents=True, exist_ok=True)
        self.issuer_priv = issuer_priv
        self.issuer_pub = pubkey_of(issuer_priv)
        self.key_id = key_id
        self.audit_id = audit_id
        self.issuer_did = issuer_did
        self.target = target or DEFAULT_TARGET
        self.property_text = property_text
        self.property_ref = property_ref or DEFAULT_PROPERTY_REF
        self._seq = 0
        if self.trail_path.exists():
            self._seq = sum(1 for ln in self.trail_path.read_text().splitlines()
                            if ln.strip())

    def emit(self, action: dict, signer_priv: bytes) -> dict:
        """Sign one crew action into a CuNi envelope and append it.

        `action` is the record of the action (hire / pay / deliver /
        denial, with actor agent_id, cost, mandate reference); the
        acting seat's key inner-signs it — tampering with the record
        after the fact breaks verification, which is demo scenario 3.
        """
        self._seq += 1
        record = {"seq": self._seq, **action}
        inner = sign_action(record, signer_priv)
        meta = {
            "audit_id": self.audit_id,
            "issued_at": _utc_now(),
            "issuer": {"auditor_did": self.issuer_did,
                       "display_name": "Accountable Agent Crew trail issuer"},
            "target": self.target,
            "property": self.property_text,
            "property_ref": self.property_ref,
        }
        env = assemble_envelope(inner, meta, self.issuer_priv, self.key_id,
                                RECEIPT_KIND)
        with self.trail_path.open("a") as f:
            f.write(json.dumps(env) + "\n")
        return env


def emit(action_receipt: dict, meta: dict, issuer_priv: bytes,
         key_id: str, receipt_kind: str = RECEIPT_KIND) -> dict:
    """Scaffold-compatible one-shot emit to the default trail path.

    NOTE: `action_receipt` must already be inner-signed (see
    sign_action); assemble_envelope rejects unsigned inner receipts.
    Prefer CrewTrail for anything beyond a single record.
    """
    env = assemble_envelope(action_receipt, meta, issuer_priv, key_id,
                            receipt_kind)
    with TRAIL_PATH.open("a") as f:
        f.write(json.dumps(env) + "\n")
    return env


def verify_trail(path: Path | str | None = None,
                 issuer_pubkey: str | None = None) -> list[dict]:
    """Verify every envelope in a trail; one result dict per line.

    This is the judges' path: no lab server, just the envelope file and
    the issuer's public key (offline mode — cuni_envelope reports key
    status as "unchecked (offline)" and never silently trusted).
    Never raises: a bad line becomes {"ok": False, ...}.
    """
    p = Path(path) if path is not None else TRAIL_PATH
    results = []
    if not p.exists():
        return [{"line": 0, "ok": False, "error": "TRAIL_MISSING",
                 "detail": f"no trail file at {p}"}]
    for i, line in enumerate(p.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            env = json.loads(line)
            res = verify_envelope(env, issuer_pubkey=issuer_pubkey)
            results.append({
                "line": i, "ok": bool(res.get("envelope_valid")),
                "verdict": res.get("verdict"),
                "checks": [c.get("name") for c in res.get("checks", [])],
                "warnings": res.get("warnings", []),
            })
        except (EnvelopeError, VerifyFailure) as e:
            results.append({"line": i, "ok": False,
                            "error": getattr(e, "code", type(e).__name__),
                            "detail": str(e)})
        except Exception as e:  # malformed JSON etc. — a result, not a crash
            results.append({"line": i, "ok": False,
                            "error": type(e).__name__, "detail": str(e)})
    return results


if __name__ == "__main__":
    raise SystemExit("library — see README.md; run the trail verify via "
                     "agent-loop/driver.py or tests/")
