#!/usr/bin/env python3
"""gate.py — the crew's spend checkpoint.

Wraps the verified Python Warrant port at
~/workspace/warrant-crossmint/warrant.py (issue_warrant / attenuate /
verify_warrant / gate_check — 8/8 integration tests pass, 2026-10-22).

Two layers, because they answer different questions:

- warrant.gate_check proves a *single* spend fits the warrant document
  (caller == effective last hop, cost <= cap, not expired). It is
  stateless: it cannot see what the same warrant already spent.
- MandateLedger (here) is the enforcement layer the scaffold TODO
  asked about: it tracks cumulative spend per warrant document
  (keyed by a fingerprint of the canonical warrant JSON) and denies
  any spend that would push the running total over the cap, even when
  each individual call would pass gate_check alone.

Every crew payment path (Rider task escrow, x402 paid call) must call
gate_payment() first. Deny by default: any failure means NO payment.
Every decision — allow and deny — is reported to the optional
on_decision callback so the caller can receipt it (the denial receipts
are half the demo). Deny codes are surfaced verbatim from the Warrant
port: WARRANT_DENIED | WARRANT_EXPIRED | OVER_BUDGET | AGENT_MISMATCH.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "workspace" / "warrant-crossmint"))
from warrant import (  # noqa: E402
    WarrantError,
    attenuate,
    gate_check,
    issue_warrant,
    verify_warrant,
)

__all__ = [
    "WarrantError",
    "MandateLedger",
    "delegate",
    "fingerprint",
    "gate_payment",
    "issue_mandate",
]


def issue_mandate(agent_id: str, max_cents: int, until: int) -> dict:
    """Issue the root mandate for a crew job (the operator's slip)."""
    return issue_warrant(
        {"agent_id": agent_id, "max_cents": max_cents, "until": until}
    )


def delegate(warrant: dict, agent_id: str, max_cents: int, until: int) -> dict:
    """Attenuate a mandate down the chain for a hired sub-agent.

    Raises WarrantError on any widening attempt — that exception IS the
    tamper/widen demo signal; callers must let it surface, not swallow it.
    """
    return attenuate(warrant, {"agent_id": agent_id, "max_cents": max_cents,
                               "until": until})


def fingerprint(warrant: dict) -> str:
    """Stable id for one warrant document (one ledger account)."""
    canon = json.dumps(warrant, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


class MandateLedger:
    """Cumulative spend tracking + gate decisions for a set of warrants.

    on_decision, if given, is called with the decision record dict on
    EVERY gate_payment() — allow and deny alike — before the decision
    is returned. Use it to emit a CuNi receipt per decision.
    """

    def __init__(self, on_decision=None):
        self._spent: dict[str, int] = {}
        self.on_decision = on_decision

    def spent_cents(self, warrant: dict) -> int:
        return self._spent.get(fingerprint(warrant), 0)

    def gate_payment(self, warrant: dict, caller_agent_id: str,
                     cost_cents: int, now: int | None = None) -> dict:
        """Approve or deny one spend, cumulative-aware.

        Returns the Warrant port's decision shape:
        {"ok": True, "body": ..., "remaining_cents": int} (remaining is
        the cumulative remainder, not the bare cap) or
        {"ok": False, "code": ..., "detail": str}.
        """
        fp = fingerprint(warrant)
        spent = self._spent.get(fp, 0)
        decision = gate_check(warrant, caller_agent_id, cost_cents, now)
        if decision["ok"]:
            cap = decision["body"]["max_cents"]
            if spent + cost_cents > cap:
                decision = {
                    "ok": False,
                    "code": "OVER_BUDGET",
                    "detail": (f"cumulative spend {spent}c + cost "
                               f"{cost_cents}c exceeds warrant cap {cap}c"),
                }
            else:
                spent += cost_cents
                self._spent[fp] = spent
                decision = {**decision, "remaining_cents": cap - spent}
        record = {
            "action": "gate.decision",
            "verdict": "ALLOW" if decision["ok"] else "DENY",
            "warrant_fingerprint": fp,
            "caller_agent_id": caller_agent_id,
            "cost_cents": cost_cents,
            "cumulative_spent_cents": self._spent.get(fp, spent),
            "ok": bool(decision["ok"]),
            "code": None if decision["ok"] else decision.get("code"),
            "detail": "" if decision["ok"] else decision.get("detail", ""),
        }
        if decision["ok"]:
            record["remaining_cents"] = decision["remaining_cents"]
        if self.on_decision is not None:
            self.on_decision(record)
        return decision


# Module-level default ledger keeps the scaffold's function API while
# still tracking cumulative spend across calls in the same process.
_default_ledger = MandateLedger()


def gate_payment(warrant: dict, caller_agent_id: str, cost_cents: int,
                 now: int | None = None, ledger: MandateLedger | None = None,
                 ) -> dict:
    """Approve or deny one spend against the default (or given) ledger."""
    return (ledger or _default_ledger).gate_payment(
        warrant, caller_agent_id, cost_cents, now)


def verify(warrant: dict, now: int | None = None) -> dict:
    """Structural verification passthrough (verify_warrant verbatim)."""
    return verify_warrant(warrant, now)


if __name__ == "__main__":
    raise SystemExit("library — see README.md")
