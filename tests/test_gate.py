#!/usr/bin/env python3
"""Mandate gate tests: single-call checks come from the verified
Warrant port; cumulative enforcement is this build's layer."""
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mandate-gate"))
import gate  # noqa: E402

NOW = 1_900_000_000
UNTIL = 2_000_000_000
LEAD = "lead-agent"
WORKER = "worker-agent"


def chain():
    root = gate.issue_mandate(LEAD, 100, UNTIL)
    hop = gate.delegate(root, WORKER, 40, UNTIL)
    return root, hop


class Attenuation(unittest.TestCase):
    def test_chain_100_40_15(self):
        root, hop = chain()
        hop2 = gate.delegate(hop, "sub-agent", 15, UNTIL)
        self.assertEqual(gate.verify(hop2, NOW)["body"]["max_cents"], 15)

    def test_widening_cents_raises(self):
        root, _ = chain()
        with self.assertRaises(gate.WarrantError):
            gate.delegate(root, WORKER, 101, UNTIL)

    def test_widening_until_raises(self):
        root, _ = chain()
        with self.assertRaises(gate.WarrantError):
            gate.delegate(root, WORKER, 40, UNTIL + 1)


class GateDecisions(unittest.TestCase):
    def setUp(self):
        self.decisions = []
        self.ledger = gate.MandateLedger(on_decision=self.decisions.append)
        _, self.hop = chain()

    def test_allow_within_cap(self):
        d = self.ledger.gate_payment(self.hop, WORKER, 2, now=NOW)
        self.assertTrue(d["ok"])
        self.assertEqual(d["remaining_cents"], 38)

    def test_cumulative_over_budget(self):
        self.assertTrue(self.ledger.gate_payment(self.hop, WORKER, 25, now=NOW)["ok"])
        d = self.ledger.gate_payment(self.hop, WORKER, 20, now=NOW)
        self.assertFalse(d["ok"])  # 25 + 20 > 40 though 20 <= 40 alone
        self.assertEqual(d["code"], "OVER_BUDGET")
        self.assertIn("cumulative", d["detail"])
        self.assertTrue(self.ledger.gate_payment(self.hop, WORKER, 15, now=NOW)["ok"])
        d = self.ledger.gate_payment(self.hop, WORKER, 1, now=NOW)
        self.assertEqual(d["code"], "OVER_BUDGET")

    def test_single_call_over_budget(self):
        d = self.ledger.gate_payment(self.hop, WORKER, 41, now=NOW)
        self.assertEqual(d["code"], "OVER_BUDGET")

    def test_agent_mismatch(self):
        d = self.ledger.gate_payment(self.hop, "someone-else", 2, now=NOW)
        self.assertEqual(d["code"], "AGENT_MISMATCH")

    def test_expired(self):
        d = self.ledger.gate_payment(self.hop, WORKER, 2, now=UNTIL + 1)
        self.assertEqual(d["code"], "WARRANT_EXPIRED")

    def test_tampered_warrant_denied(self):
        import copy
        bad = copy.deepcopy(self.hop)
        bad["hops"][-1]["max_cents"] = 999  # hand-widened hop
        d = self.ledger.gate_payment(bad, WORKER, 2, now=NOW)
        self.assertFalse(d["ok"])
        self.assertEqual(d["code"], "WARRANT_DENIED")

    def test_denied_spend_is_not_booked(self):
        self.ledger.gate_payment(self.hop, WORKER, 41, now=NOW)
        self.assertEqual(self.ledger.spent_cents(self.hop), 0)

    def test_every_decision_is_reported(self):
        self.ledger.gate_payment(self.hop, WORKER, 2, now=NOW)
        self.ledger.gate_payment(self.hop, WORKER, 99, now=NOW)
        self.assertEqual(len(self.decisions), 2)
        self.assertEqual([d["verdict"] for d in self.decisions],
                         ["ALLOW", "DENY"])
        self.assertEqual(self.decisions[0]["cumulative_spent_cents"], 2)


class ModuleApi(unittest.TestCase):
    def test_module_level_gate_tracks_cumulative(self):
        w = gate.issue_mandate("mod-lead", 10, int(time.time()) + 600)
        self.assertTrue(gate.gate_payment(w, "mod-lead", 7)["ok"])
        d = gate.gate_payment(w, "mod-lead", 7)
        self.assertEqual(d["code"], "OVER_BUDGET")


if __name__ == "__main__":
    unittest.main()
