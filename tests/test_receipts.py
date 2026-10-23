#!/usr/bin/env python3
"""Receipt trail tests: emit -> verify whole trail; tamper detection."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "receipts"))
import receipts  # noqa: E402


class TrailTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        keys = Path(self.tmp.name) / "keys"
        self.issuer_priv, self.issuer_pub = receipts.ensure_keypair(keys, "issuer")
        self.seat_priv, self.seat_pub = receipts.ensure_keypair(keys, "seat-a")
        self.path = Path(self.tmp.name) / "trail.jsonl"
        self.trail = receipts.CrewTrail(
            self.path, self.issuer_priv, key_id="test:issuer",
            audit_id="accountable-crew/test-run",
            issuer_did="did:agent-rider:testlead")

    def tearDown(self):
        self.tmp.cleanup()

    def _emit3(self):
        self.trail.emit({"action": "hire.posted", "verdict": "RECORDED",
                         "actor_agent_id": "lead1", "task_id": "tsk_1",
                         "reward_agc": 5}, self.seat_priv)
        self.trail.emit({"action": "gate.decision", "verdict": "ALLOW",
                         "actor_agent_id": "worker1", "cost_cents": 2,
                         "ok": True, "code": None}, self.seat_priv)
        self.trail.emit({"action": "hire.approved", "verdict": "RECORDED",
                         "actor_agent_id": "lead1", "task_id": "tsk_1",
                         "credits_earned": 5}, self.seat_priv)

    def test_whole_trail_verifies(self):
        self._emit3()
        results = receipts.verify_trail(self.path, issuer_pubkey=self.issuer_pub)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r["ok"] for r in results), results)
        self.assertTrue(all(r["verdict"] == "RECORDED" or r["verdict"]
                            for r in results))

    def test_tampered_line_fails_verification(self):
        self._emit3()
        lines = self.path.read_text().splitlines()
        env = json.loads(lines[1])
        env["tool_receipt"]["cost_cents"] = 9999  # post-hoc edit
        lines[1] = json.dumps(env)
        self.path.write_text("\n".join(lines) + "\n")
        results = receipts.verify_trail(self.path, issuer_pubkey=self.issuer_pub)
        self.assertTrue(results[0]["ok"])
        self.assertFalse(results[1]["ok"])
        self.assertEqual(results[1]["error"], "TAMPERRED_INNER")
        self.assertTrue(results[2]["ok"])

    def test_wrong_issuer_pubkey_fails(self):
        self._emit3()
        _, other_pub = receipts.ensure_keypair(Path(self.tmp.name) / "k2", "x")
        results = receipts.verify_trail(self.path, issuer_pubkey=other_pub)
        self.assertTrue(all(not r["ok"] for r in results))

    def test_floats_are_canon_safe(self):
        env = self.trail.emit({"action": "x402.terms", "verdict": "RECORDED",
                               "actor_agent_id": "worker1",
                               "price_cents": 2.0, "ratio": 0.5},
                              self.seat_priv)
        self.assertEqual(env["tool_receipt"]["price_cents"], 2)
        self.assertEqual(env["tool_receipt"]["ratio"], "0.5")
        results = receipts.verify_trail(self.path, issuer_pubkey=self.issuer_pub)
        self.assertTrue(results[0]["ok"])

    def test_missing_trail_is_a_result_not_a_crash(self):
        results = receipts.verify_trail(Path(self.tmp.name) / "nope.jsonl",
                                        issuer_pubkey=self.issuer_pub)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["ok"])

    def test_keypair_files_are_0600_and_stable(self):
        import os
        import stat
        keys = Path(self.tmp.name) / "keys"
        mode = stat.S_IMODE(os.stat(keys / "issuer.key").st_mode)
        self.assertEqual(mode, 0o600)
        priv2, pub2 = receipts.ensure_keypair(keys, "issuer")
        self.assertEqual(priv2, self.issuer_priv)
        self.assertEqual(pub2, self.issuer_pub)


if __name__ == "__main__":
    unittest.main()
