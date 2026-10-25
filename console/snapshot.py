#!/usr/bin/env python3
"""snapshot.py — build console/snapshot.js from real crew artifacts only.

Inputs (all real, no invented shapes):
  1. runs/<run-id>/trail.jsonl — CuNi check envelopes from a live run
  2. tasks.json — live open-task list (GET /api/tasks), fetched separately
Output:
  console/snapshot.js — `const CREW_SNAPSHOT = {...}` embedded for index.html

Structural checks only. Cryptographic verification is NOT performed here;
it needs receipts.py + the fabric-phase1 cuni_envelope dep. The snapshot
says so explicitly (verify.status = "pending-dep").
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_TOP = ["envelope_version", "receipt_kind", "audit_id", "issued_at",
                "issuer", "target", "property", "tool_receipt",
                "tool_receipt_sha256", "envelope_signature"]


def load_trail(path):
    envs = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line:
            envs.append(json.loads(line))
    return envs


def main():
    trail_path = Path(sys.argv[1])
    tasks_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("snapshot.js")
    envs = load_trail(trail_path)

    seqs = [e.get("tool_receipt", {}).get("seq") for e in envs]
    checks = {
        "envelope_count": len(envs),
        "seq_contiguous_1_to_n": seqs == list(range(1, len(envs) + 1)),
        "required_keys_present": all(
            all(k in e for k in REQUIRED_TOP) for e in envs),
        "distinct_envelope_signatures": len(
            {e.get("envelope_signature") for e in envs}) == len(envs),
    }

    seats = {}
    mandates = {}
    decisions = []
    actions_seen = []
    for e in envs:
        tr = e.get("tool_receipt", {})
        action = tr.get("action", "?")
        actions_seen.append(action)
        for key in ("lead_agent_id", "researcher_agent_id",
                    "holder_agent_id", "caller_agent_id"):
            aid = tr.get(key)
            if aid:
                seats.setdefault(aid, {"actions": []})["actions"].append(action)
        if action == "mandate.issued":
            fp = tr.get("warrant_fingerprint", "?")
            mandates[fp] = {"cap_cents": tr.get("cap_cents"),
                            "holder": tr.get("holder_agent_id")}
        if action == "gate.decision":
            decisions.append({
                "verdict": tr.get("verdict"),
                "warrant_fingerprint": tr.get("warrant_fingerprint"),
                "caller_agent_id": tr.get("caller_agent_id"),
                "cost_cents": tr.get("cost_cents"),
            })

    tasks = []
    if tasks_path and tasks_path.exists():
        doc = json.loads(tasks_path.read_text())
        for t in doc.get("tasks", []):
            tasks.append({"id": t.get("id"), "title": t.get("title"),
                          "reward": t.get("reward"),
                          "category": t.get("category")})

    snap = {
        "generated_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "run_id": (envs[0].get("audit_id") if envs else None),
        "envelope_version": (envs[0].get("envelope_version") if envs else None),
        "checks": checks,
        "actions_seen": sorted(set(actions_seen)),
        "seats": [{"agent_id": k, "actions": v["actions"]}
                  for k, v in sorted(seats.items())],
        "mandates": [{"fingerprint": k, **v}
                     for k, v in sorted(mandates.items())],
        "decisions": decisions,
        "receipts": [{"seq": e.get("tool_receipt", {}).get("seq"),
                      "action": e.get("tool_receipt", {}).get("action"),
                      "verdict": e.get("tool_receipt", {}).get("verdict"),
                      "issued_at": e.get("issued_at"),
                      "fingerprint_sha256": e.get("tool_receipt_sha256"),
                      "envelope_signature": e.get("envelope_signature")}
                     for e in envs],
        "tasks_open": tasks,
        "verify": {"status": "pending-dep",
                   "detail": "Cryptographic verify needs receipts.py + "
                             "fabric-phase1 cuni_envelope (absent on this "
                             "host). Structural checks above are local."},
    }
    out_path.write_text("const CREW_SNAPSHOT = " +
                        json.dumps(snap, indent=1) + ";\n")
    print("snapshot: %d envelopes, %d seats, %d mandates, %d decisions, "
          "%d tasks -> %s"
          % (len(envs), len(seats), len(mandates), len(decisions),
             len(tasks), out_path))


if __name__ == "__main__":
    main()
