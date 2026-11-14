#!/usr/bin/env python3
"""demo_testnet.py — NEAR testnet dry-run for the Accountable Agent Crew.

Do X, see Y:
  python3 near-rail/demo_testnet.py [--signer <near-account>]
    -> builds a mandate (lead 100c, worker 40c), gates a NEAR Intents
       swap declaration (default: wrap.testnet -> usdc.fakes.testnet,
       example testnet asset ids, illustrative amounts only), probes
       the public testnet RPC (read-only `status`), attempts the Chain
       Signatures request (NOT sent — no MPC contract configured),
       and writes runs/near-testnet-dryrun-<ts>.json.

What you will see in the receipt file: the intent object, the gate
decision (ALLOW, remaining_cents), the testnet RPC status
(reachable + chain_id + latest block, or reachable=False with the
error), and signature status NOT_SIGNED with the exact request that
was not sent. Nothing is quoted, signed, broadcast, or settled.
The payout account printed is Corey's NEAR account, supplied
2026-11-14 (64-hex implicit account id).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mandate-gate"))
sys.path.insert(0, str(ROOT / "near-rail"))
import gate  # noqa: E402
import near_intents as ni  # noqa: E402

# Corey's NEAR payout account (implicit, 64-hex), supplied 2026-11-14.
# It names the account on testnet and mainnet alike; the leg itself
# only ever runs against testnet.
PAYOUT_ACCOUNT = "7cdb35e939ee4e51a7b47f8b411335ea683f7ec6285f4e73a1e35ad9b902719d"

LEAD = "crew-lead"
WORKER = "crew-researcher"
NOW = int(time.time())
UNTIL = NOW + 3600


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--signer", default=PAYOUT_ACCOUNT,
                    help="NEAR signer account id (default: payout account)")
    ap.add_argument("--asset-in", default="wrap.testnet")
    ap.add_argument("--asset-out", default="usdc.fakes.testnet")
    ap.add_argument("--amount-in", type=int, default=1_000_000)
    ap.add_argument("--cost-cents", type=int, default=2)
    ap.add_argument("--mpc-contract", default=os.environ.get("NEAR_MPC_CONTRACT"),
                    help="testnet MPC contract, if configured (default: none)")
    args = ap.parse_args()

    decisions = []
    ledger = gate.MandateLedger(on_decision=decisions.append)
    root = gate.issue_mandate(LEAD, 100, UNTIL)
    hop = gate.delegate(root, WORKER, 40, UNTIL)

    intent = ni.build_intent(args.signer, args.asset_in, args.asset_out,
                             args.amount_in)
    gated = ni.gate_intent(ledger, hop, WORKER, args.cost_cents, intent,
                           now=NOW)
    rpc = ni.check_testnet_status()

    path = ni.chain_signature_derivation_path()
    try:
        sig_request = ni.chain_signature_request(intent, path,
                                                 args.mpc_contract)
        sig_status = {"status": "REQUEST_BUILT_NOT_SENT",
                      "request": sig_request}
    except ni.NearNotConfigured as e:
        sig_status = {"status": "NOT_SIGNED",
                      "reason": str(e),
                      "request_not_sent": e.request}
    except ni.NearError as e:
        sig_status = {"status": "ERROR", "reason": str(e)}

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "runs"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"near-testnet-dryrun-{ts}.json"
    receipt = {
        "demo": "near-testnet-dryrun",
        "network": ni.NETWORK,
        "run_at_utc": ts,
        "payout_account": PAYOUT_ACCOUNT,
        "signer_id": args.signer,
        "intent": intent,
        "intent_payload_hash_hex": ni.intent_payload_hash(intent).hex(),
        "gate": gated,
        "gate_decisions": decisions,
        "testnet_rpc": rpc,
        "chain_signatures": sig_status,
        "derivation_path": path,
        "honesty": ("TESTNET DRY-RUN ONLY. No solver quote fetched, no "
                    "signature produced, nothing broadcast or settled. "
                    "Asset ids/amounts are illustrative dry-run values."),
    }
    out_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"gate: {'ALLOW' if gated['gate']['ok'] else 'DENY'} "
          f"(remaining {gated.get('remaining_cents')}c)")
    print(f"testnet rpc: reachable={rpc['reachable']} "
          f"chain_id={rpc.get('chain_id')} "
          f"block={rpc.get('latest_block_height')}")
    print(f"chain signatures: {sig_status['status']}")
    print(f"receipt: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
