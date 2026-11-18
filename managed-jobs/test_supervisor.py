#!/usr/bin/env python3
"""Supervisor v1 tests. Pure stdlib unittest, no network, no cloud, no
keys. Run: python3 test_supervisor.py (from this directory)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supervisor as S  # noqa: E402


def make_job(sup):
    return S.new_job(
        job_id="t-1", owner="corey", objective="pilot",
        acceptance_tests=[{"name": "canary"}, {"name": "seam"}],
        authority_reference="cap-approval", budget_reserved=25.0,
        escalation_owner="corey")


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def now(self):
        return self.t


class TestSupervisor(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.reg = S.CapabilityRegistry(now_fn=self.clock.now)
        self.reg.register("exec-good", "runpod-h200", "py3.13+jax",
                          {"runpod": True, "jupyter": True},
                          ["launch", "stop"], ["describe"])
        self.reg.register("exec-docs", "docs-box", "py3.11",
                          {"runpod": False},
                          [], ["launch", "stop"])
        self.sup = S.Supervisor(registry=self.reg, now_fn=self.clock.now)
        self.job = make_job(self.sup)

    def drive_to_running(self, executor="exec-good"):
        ok, _ = self.sup.check_capabilities(self.job, executor,
                                            ["runpod"], ["launch"])
        self.assertTrue(ok)
        self.sup.claim(self.job, executor)
        self.sup.heartbeat(self.job)
        self.assertEqual(self.job["state"], S.RUNNING)

    def test_submit_and_capability_block(self):
        self.assertEqual(self.job["state"], S.SUBMITTED)
        ok, missing = self.sup.check_capabilities(self.job, "exec-docs",
                                                  ["runpod"], ["launch"])
        self.assertFalse(ok)
        self.assertIn("tool not authenticated: runpod", missing)
        self.assertIn("action can only be described, not performed: launch",
                      missing)
        self.assertEqual(self.job["state"], S.BLOCKED)
        with self.assertRaises(S.IllegalTransition):
            self.sup.claim(self.job, "exec-docs")

    def test_capability_pass_claim_heartbeat(self):
        self.drive_to_running()
        first_lease = self.job["lease_expiry"]
        self.clock.t += 600
        self.sup.heartbeat(self.job)
        self.assertGreater(self.job["lease_expiry"], first_lease)

    def test_illegal_transitions(self):
        with self.assertRaises(S.IllegalTransition):
            self.sup.heartbeat(self.job)  # SUBMITTED, never claimed
        with self.assertRaises(S.IllegalTransition):
            self.sup.complete(self.job, {}, {})

    def test_lease_expiry_abandons_and_revokes(self):
        self.drive_to_running()
        self.clock.t += S.DEFAULT_LEASE_SECONDS + 1
        self.assertTrue(self.sup.expire_lease(self.job))
        self.assertEqual(self.job["state"], S.ABANDONED)
        self.assertTrue(self.job["authority_revoked"])
        with self.assertRaises(S.BudgetRefused):
            self.sup.record_spend(self.job, "a1", 1.0)

    def test_resume_requires_reconcile(self):
        self.drive_to_running()
        self.clock.t += S.DEFAULT_LEASE_SECONDS + 1
        self.sup.expire_lease(self.job)
        with self.assertRaises(S.ResumeRequiresReconcile):
            self.sup.claim(self.job, "exec-good")
        self.sup.reconcile(self.job, {"provision": "pod exists"})
        self.sup.claim(self.job, "exec-good")
        self.assertEqual(self.job["state"], S.CLAIMED)

    def test_budget_hard_stop_and_idempotency(self):
        self.drive_to_running()
        self.assertTrue(self.sup.record_spend(self.job, "p1", 21.0))
        self.assertFalse(self.sup.record_spend(self.job, "p1", 21.0))
        self.assertEqual(self.job["budget_consumed"], 21.0)
        with self.assertRaises(S.BudgetRefused):
            self.sup.record_spend(self.job, "p2", 5.0)  # 21 + 5 > 25

    def test_reconcile_never_double_counts_spend(self):
        self.drive_to_running()
        self.sup.record_spend(self.job, "p1", 10.0)
        self.sup.reconcile(self.job, {}, observed_spend_total=10.0)
        self.assertEqual(self.job["budget_consumed"], 10.0)
        self.sup.reconcile(self.job, {}, observed_spend_total=12.5)
        self.assertEqual(self.job["budget_consumed"], 12.5)

    def test_retry_skips_completed_actions(self):
        self.drive_to_running()
        self.assertTrue(self.sup.record_action(self.job, "up1", "done"))
        self.assertFalse(self.sup.record_action(self.job, "up1", "done"))

    def test_acceptance_gate_executor_is_not_verdict(self):
        self.drive_to_running()
        # Executor claims done; verifiers disagree -> stays RUNNING.
        ok, failed = self.sup.complete(
            self.job, {"executor_says": "done"},
            {"canary": lambda e: False, "seam": lambda e: True})
        self.assertFalse(ok)
        self.assertEqual(failed, ["canary"])
        self.assertEqual(self.job["state"], S.RUNNING)
        ok, failed = self.sup.complete(
            self.job, {"canary_evidence": "pass", "seam_evidence": "pass"},
            {"canary": lambda e: True, "seam": lambda e: True})
        self.assertTrue(ok)
        self.assertEqual(self.job["state"], S.COMPLETED)

    def test_teardown_proof_required_for_resource_jobs(self):
        self.drive_to_running()
        self.job["resource_id"] = "pod-xyz"
        ok, failed = self.sup.complete(
            self.job, {}, {"canary": lambda e: True,
                           "seam": lambda e: True})
        self.assertFalse(ok)
        self.assertIn("teardown_proof_missing", failed)
        self.job["teardown_proof"] = {"action": "stopped",
                                      "final_cost_usd": 21.16}
        ok, _ = self.sup.complete(
            self.job, {}, {"canary": lambda e: True,
                           "seam": lambda e: True})
        self.assertTrue(ok)

    def test_cancel_revokes_and_requires_teardown(self):
        self.drive_to_running()
        self.job["resource_id"] = "pod-xyz"
        self.sup.cancel(self.job, "pilot kill read")
        self.assertEqual(self.job["state"], S.CANCELLED)
        self.assertTrue(self.job["authority_revoked"])
        self.assertIn("pod-xyz", self.job["next_action"])
        with self.assertRaises(S.IllegalTransition):
            self.sup.cancel(self.job, "again")

    def test_capability_staleness_blocks(self):
        stale = S.CapabilityRegistry(now_fn=self.clock.now, ttl=60)
        stale.register("exec-old", "box", "py", {"runpod": True},
                       ["launch"], [], last_tested_at=self.clock.now() - 3600)
        sup = S.Supervisor(registry=stale, now_fn=self.clock.now)
        job = make_job(sup)
        ok, missing = sup.check_capabilities(job, "exec-old",
                                             ["runpod"], ["launch"])
        self.assertFalse(ok)
        self.assertTrue(any("stale" in m for m in missing))

    def test_final_record_hash_stable_and_tamper_visible(self):
        self.drive_to_running()
        self.sup.complete(self.job, {},
                          {"canary": lambda e: True,
                           "seam": lambda e: True})
        rec1 = self.sup.final_record(self.job)
        rec2 = self.sup.final_record(self.job)
        self.assertEqual(rec1["sha256"], rec2["sha256"])
        tampered = dict(self.job)
        tampered["budget_consumed"] = 999.0
        digest = S.hashlib.sha256(
            S.json.dumps({k: tampered[k] for k in sorted(tampered)},
                         sort_keys=True,
                         separators=(",", ":")).encode()).hexdigest()
        self.assertNotEqual(digest, rec1["sha256"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
