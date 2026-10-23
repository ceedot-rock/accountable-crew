#!/usr/bin/env python3
"""driver.py — deterministic Scenario 1 run of the Accountable Agent Crew.

No model is involved: the plan comes from the "scripted" provider
(providers.py — deterministic, labeled as such in every receipt).
Everything else is real and live:

  hire      lead posts a task on the Agent-Rider rail (5 AGC escrowed),
            researcher claims it (1 AGC claim cost)
  research  researcher fetches the LIVE x402 402-terms for the PCC
            info endpoint from rider-x402.fly.dev
  gate      the spend (the terms' price) is checked against the
            researcher's attenuated Warrant mandate (root 100c ->
            researcher hop 40c) by mandate-gate, cumulative-aware;
            the decision is receipted either way
  pay       the x402 paid call executes IF a payer key is configured
            (env CREW_X402_PAYER_KEY). Without one the stage records
            BLOCKED with the captured terms — it is never faked.
  settle    researcher submits the result; lead approves; escrow
            releases on the live rail
  verify    every CuNi receipt in the run's trail is re-verified
            offline (issuer pubkey only); any failure fails the run

Every cross-agent action is receipted into runs/<run-id>/trail.jsonl.
Exit 0 = every executed stage passed and the whole trail verified.
A BLOCKED payment stage is reported loudly but does not fail the run:
it is an environment blocker (no funded payer key), not a code path
failure — the distinction is the point of the exercise.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))                 # agent_loop, providers, driver
sys.path.insert(0, str(ROOT / "mandate-gate"))  # gate, paid_call, ethsig
sys.path.insert(0, str(ROOT / "receipts"))      # receipts

import gate as gate_mod          # noqa: E402
import paid_call                 # noqa: E402
import receipts as trail_mod     # noqa: E402
from agent_loop import CrewAgent  # noqa: E402

JOB = ("Find out what the PCC info endpoint costs, in cents, and prove "
       "the crew can pay for it under a Warrant mandate.")
SCRIPT = [{
    "title": "Fetch the PCC info price via the x402 rail",
    "assignee_hint": "crew-researcher",
    "budget_cents": 2,
}]
ROOT_CAP_CENTS = 100
HOP_CAP_CENTS = 40
TASK_REWARD_AGC = 5


def main() -> int:
    run_id = time.strftime("run-%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    trail_path = run_dir / "trail.jsonl"
    stages: list[tuple[str, str]] = []

    def stage(name: str, status: str, detail: str = ""):
        stages.append((name, status))
        print(f"[{status:>7}] {name}" + (f" — {detail}" if detail else ""))

    # --- keys + trail -------------------------------------------------
    keys_dir = ROOT / ".keys"
    issuer_priv, issuer_pub = trail_mod.ensure_keypair(keys_dir, "trail-issuer")
    lead_ed_priv, _ = trail_mod.ensure_keypair(keys_dir, "crew-lead-ed")
    res_ed_priv, _ = trail_mod.ensure_keypair(keys_dir, "crew-researcher-ed")

    # --- seats ----------------------------------------------------------
    lead = CrewAgent("crew-lead", capabilities=["coordinate", "plan", "hire"])
    researcher = CrewAgent("crew-researcher",
                           capabilities=["research", "synthesize"])
    lead_reg = lead.register()
    res_reg = researcher.register()
    lead_id = lead.agent_id
    res_id = researcher.agent_id
    lead_ok = lead.verify_identity().get("valid")
    res_ok = researcher.verify_identity().get("valid")
    stage("seats", "OK" if (lead_ok and res_ok) else "FAIL",
          f"lead={lead_id} researcher={res_id} verified={lead_ok}/{res_ok}")
    if not (lead_ok and res_ok):
        return 1

    trail = trail_mod.CrewTrail(
        trail_path, issuer_priv, key_id="crew:trail-issuer:2026-10",
        audit_id=f"accountable-crew/{run_id}",
        issuer_did=f"did:agent-rider:{lead_id}")
    seat_keys = {lead_id: lead_ed_priv, res_id: res_ed_priv}

    def emit(action: dict, actor_id: str):
        return trail.emit(action, seat_keys[actor_id])

    emit({"action": "run.started", "verdict": "RECORDED", "job": JOB,
          "lead_agent_id": lead_id, "researcher_agent_id": res_id,
          "provider": "scripted (deterministic, no model)",
          "lead_register": {k: v for k, v in lead_reg.items()},
          "researcher_register": {k: v for k, v in res_reg.items()}}, lead_id)

    # --- mandate --------------------------------------------------------
    until = int(time.time()) + 7200
    root = gate_mod.issue_mandate(lead_id, ROOT_CAP_CENTS, until)
    emit({"action": "mandate.issued", "verdict": "RECORDED",
          "holder_agent_id": lead_id, "cap_cents": ROOT_CAP_CENTS,
          "warrant_fingerprint": gate_mod.fingerprint(root)}, lead_id)
    hop = gate_mod.delegate(root, res_id, HOP_CAP_CENTS, until)
    emit({"action": "mandate.delegated", "verdict": "RECORDED",
          "from_agent_id": lead_id, "to_agent_id": res_id,
          "cap_cents": HOP_CAP_CENTS,
          "warrant_fingerprint": gate_mod.fingerprint(hop)}, lead_id)
    stage("mandate", "OK", f"root {ROOT_CAP_CENTS}c (lead) -> hop "
                           f"{HOP_CAP_CENTS}c (researcher)")

    # --- plan (scripted provider, no model) ------------------------------
    plan = lead.plan(JOB, {"script": SCRIPT}, provider="scripted")
    emit({"action": "plan.created", "verdict": "RECORDED",
          "provider": "scripted (deterministic, no model)",
          "subtasks": plan}, lead_id)
    stage("plan", "OK", f"{len(plan)} subtask(s) via scripted provider")

    # --- hire on the live rail -------------------------------------------
    posted = lead.post_task(
        title=f"[crew-e2e] {plan[0]['title']}",
        description=JOB, reward_agc=TASK_REWARD_AGC, category="general",
        input_obj={"job": JOB, "subtask": plan[0]},
        acceptance="State the PCC info price in cents and how payment "
                   "was gated and executed (or why it was blocked).")
    task = posted.get("task", posted)
    task_id = task["id"]
    emit({"action": "hire.posted", "verdict": "RECORDED",
          "task_id": task_id, "reward_agc": TASK_REWARD_AGC,
          "poster_agent_id": lead_id}, lead_id)
    stage("hire.post", "OK", f"task {task_id}, {TASK_REWARD_AGC} AGC escrowed")

    claimed = researcher.claim_task(task_id)
    emit({"action": "hire.claimed", "verdict": "RECORDED",
          "task_id": task_id, "worker_agent_id": res_id}, res_id)
    stage("hire.claim", "OK", f"claimed by researcher {res_id}")

    # --- x402 terms (live, unpaid) ----------------------------------------
    terms = paid_call.fetch_terms(paid_call.PCC_INFO_URL, {})
    price_cents = paid_call.terms_price_cents(terms)
    emit({"action": "x402.terms", "verdict": "RECORDED",
          "url": terms["url"], "network": terms["network"],
          "amount_base_units": terms["amount_base_units"],
          "price_cents": price_cents, "asset": terms["asset"],
          "pay_to": terms["pay_to"], "resource": terms["resource"]}, res_id)
    stage("x402.terms", "OK", f"{price_cents}c on {terms['network']} "
                              f"(payTo {terms['pay_to']})")

    # --- mandate gate ------------------------------------------------------
    ledger = gate_mod.MandateLedger(
        on_decision=lambda rec: emit(rec, rec["caller_agent_id"]))
    decision = ledger.gate_payment(hop, res_id, price_cents)
    if not decision["ok"]:
        stage("gate", "FAIL", f"denied: {decision}")
        return 1
    stage("gate", "OK", f"allowed {price_cents}c; cumulative remaining "
                        f"{decision['remaining_cents']}c")

    # --- payment -----------------------------------------------------------
    payer_key = os.environ.get("CREW_X402_PAYER_KEY")
    payment_status = "not_executed"
    payment_detail = ""
    try:
        result = paid_call.paid_call(paid_call.PCC_INFO_URL, {}, payer_key)
        payment_status = "executed"
        payment_detail = f"tx {result['tx_hash']}, HTTP {result['status']}"
        emit({"action": "x402.payment", "verdict": "RECORDED",
              "status": payment_status, "tx_hash": result["tx_hash"],
              "payer": result["payer"], "http_status": result["status"],
              "price_cents": price_cents}, res_id)
        result_text = (
            f"PCC info endpoint price: {price_cents} cents (native USDC "
            f"on {terms['network']}), per live 402 terms at "
            f"{terms['url']}. Paid under Warrant mandate "
            f"(hop cap {HOP_CAP_CENTS}c): tx {result['tx_hash']}, "
            f"service answered HTTP {result['status']}.")
    except paid_call.PaidCallNotFunded as e:
        payment_status = "blocked_no_payer_key"
        payment_detail = str(e)
        emit({"action": "x402.payment", "verdict": "RECORDED",
              "status": payment_status, "reason": str(e),
              "price_cents": price_cents, "network": terms["network"],
              "pay_to": terms["pay_to"]}, res_id)
        result_text = (
            f"PCC info endpoint price: {price_cents} cents (native USDC "
            f"on {terms['network']}), per live 402 terms at "
            f"{terms['url']}. The spend was APPROVED by the Warrant "
            f"mandate gate (hop cap {HOP_CAP_CENTS}c), but the payment "
            "itself was NOT executed in this run: no funded payer key "
            "is configured for the crew (CREW_X402_PAYER_KEY unset). "
            "Terms were captured and the gate decision receipted; the "
            "payment leg is blocked on key custody, not on the gate.")
    stage("x402.pay", "OK" if payment_status == "executed" else "BLOCKED",
          payment_detail or payment_status)

    # --- settle on the rail --------------------------------------------------
    submitted = researcher.submit_task(task_id, result_text)
    emit({"action": "hire.submitted", "verdict": "RECORDED",
          "task_id": task_id, "worker_agent_id": res_id,
          "rail_status": submitted.get("status")}, res_id)
    stage("hire.submit", "OK", f"status={submitted.get('status')}")

    approved = lead.approve_task(task_id)
    emit({"action": "hire.approved", "verdict": "RECORDED",
          "task_id": task_id, "poster_agent_id": lead_id,
          "credits_earned": approved.get("creditsEarned"),
          "fee_charged": approved.get("feeCharged"),
          "worker_credits_total": approved.get("creditsTotal")}, lead_id)
    stage("hire.approve", "OK",
          f"worker earned {approved.get('creditsEarned')} AGC")

    lead_bal = lead.balance().get("credits")
    res_bal = researcher.balance().get("credits")
    emit({"action": "run.finished", "verdict": "RECORDED",
          "lead_credits": lead_bal, "researcher_credits": res_bal,
          "payment_status": payment_status}, lead_id)
    stage("balances", "OK", f"lead={lead_bal} AGC, researcher={res_bal} AGC")

    # --- verify the whole trail ----------------------------------------------
    results = trail_mod.verify_trail(trail_path, issuer_pubkey=issuer_pub)
    bad = [r for r in results if not r["ok"]]
    for r in results:
        print(f"    verify line {r['line']}: "
              + ("OK" if r["ok"] else f"FAIL {r.get('error')}: {r.get('detail')}"))
    stage("verify", "OK" if not bad else "FAIL",
          f"{len(results) - len(bad)}/{len(results)} receipts verified")
    print(f"\ntrail: {trail_path}")
    print(f"issuer pubkey: {issuer_pub}")
    failed = [n for n, s in stages if s == "FAIL"]
    blocked = [n for n, s in stages if s == "BLOCKED"]
    print("summary: " + json.dumps({"stages": stages, "failed": failed,
                                    "blocked": blocked}))
    return 1 if (failed or bad) else 0


if __name__ == "__main__":
    raise SystemExit(main())
