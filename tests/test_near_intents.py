#!/usr/bin/env python3
"""NEAR testnet leg tests: intent shape, mandate gating, Chain
Signatures request building, and the read-only testnet RPC probe.
All live-network behaviour is tested through an injected opener —
no test touches the real network."""
import hashlib
import json
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mandate-gate"))
sys.path.insert(0, str(ROOT / "near-rail"))
import gate  # noqa: E402
import near_intents as ni  # noqa: E402

SIGNER = "7cdb35e939ee4e51a7b47f8b411335ea683f7ec6285f4e73a1e35ad9b902719d"
NAMED = "crew.testnet"
NOW = 1_900_000_000
UNTIL = 2_000_000_000


def intent(**kw):
    args = {"signer_id": SIGNER, "asset_in": "wrap.testnet",
            "asset_out": "usdc.fakes.testnet", "amount_in": 1_000_000}
    args.update(kw)
    return ni.build_intent(**args)


def ledger_with_hop(cap=40):
    decisions = []
    ledger = gate.MandateLedger(on_decision=decisions.append)
    root = gate.issue_mandate("lead", 100, UNTIL)
    hop = gate.delegate(root, "worker", cap, UNTIL)
    return ledger, hop, decisions


class BuildIntent(unittest.TestCase):
    def test_structure(self):
        it = intent()
        self.assertEqual(it["network"], "testnet")
        self.assertEqual(it["signer_id"], SIGNER)
        self.assertEqual(it["status"], "dry-run")
        self.assertEqual(it["execution"], "NOT_EXECUTED")
        self.assertEqual(it["intents"][0]["intent"], "token_diff")
        self.assertEqual(it["intents"][0]["diff"]["wrap.testnet"], "-1000000")

    def test_named_account_accepted(self):
        self.assertEqual(intent(signer_id=NAMED)["signer_id"], NAMED)

    def test_bad_signer_rejected(self):
        with self.assertRaises(ni.NearError):
            intent(signer_id="BAD SIGNER!")
        with self.assertRaises(ni.NearError):
            intent(signer_id="x")

    def test_bad_amount_rejected(self):
        for bad in (0, -5, 1.5, "1000", True):
            with self.assertRaises(ni.NearError, msg=str(bad)):
                intent(amount_in=bad)

    def test_past_deadline_rejected(self):
        with self.assertRaises(ni.NearError):
            intent(deadline_ms=int(time.time() * 1000) - 1000)

    def test_min_out_recorded(self):
        it = intent(min_amount_out=900_000)
        self.assertEqual(it["intents"][0]["diff"]["usdc.fakes.testnet"],
                         "+900000")

    def test_json_serializable_no_floats(self):
        raw = json.dumps(intent())
        back = json.loads(raw)
        self.assertEqual(back["intents"][0]["diff"]["wrap.testnet"],
                         "-1000000")


class PayloadHash(unittest.TestCase):
    def test_deterministic_32_bytes(self):
        h1 = ni.intent_payload_hash(intent())
        h2 = ni.intent_payload_hash(intent())
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 32)
        self.assertEqual(
            h1.hex(),
            hashlib.sha256(json.dumps(
                intent(), sort_keys=True,
                separators=(",", ":")).encode()).hexdigest())

    def test_nonce_changes_hash(self):
        self.assertNotEqual(
            ni.intent_payload_hash(intent()),
            ni.intent_payload_hash(intent(nonce="different-nonce")))


class DerivationPath(unittest.TestCase):
    def test_default(self):
        self.assertEqual(ni.chain_signature_derivation_path(),
                         "44'/397'/0'/0'/1'")

    def test_indices(self):
        self.assertEqual(
            ni.chain_signature_derivation_path(2, 3, 4),
            "44'/397'/2'/3'/4'")

    def test_negative_rejected(self):
        with self.assertRaises(ni.NearError):
            ni.chain_signature_derivation_path(-1)


class SignatureRequest(unittest.TestCase):
    def test_unconfigured_raises_with_request(self):
        with self.assertRaises(ni.NearNotConfigured) as ctx:
            ni.chain_signature_request(intent(), "44'/397'/0'/0'/1'")
        req = ctx.exception.request
        self.assertIsNone(req["contract"])
        self.assertEqual(req["method"], "sign")
        self.assertEqual(len(req["args"]["payload"]), 32)
        self.assertEqual(req["args"]["key_version"], 0)

    def test_configured_builds_call(self):
        req = ni.chain_signature_request(
            intent(), "44'/397'/0'/0'/1'",
            mpc_contract="v1.signer-prod.testnet")
        self.assertEqual(req["contract"], "v1.signer-prod.testnet")
        self.assertEqual(req["network"], "testnet")


class GateIntent(unittest.TestCase):
    def test_allow_marks_dry_run(self):
        ledger, hop, _ = ledger_with_hop()
        rec = ni.gate_intent(ledger, hop, "worker", 2, intent(), now=NOW)
        self.assertTrue(rec["gate"]["ok"])
        self.assertFalse(rec["executed"])
        self.assertEqual(rec["remaining_cents"], 38)
        self.assertIn("dry-run", rec["execution"])

    def test_deny_blocks_everything(self):
        ledger, hop, _ = ledger_with_hop()
        rec = ni.gate_intent(ledger, hop, "worker", 41, intent(), now=NOW)
        self.assertFalse(rec["gate"]["ok"])
        self.assertEqual(rec["gate"]["code"], "OVER_BUDGET")
        self.assertFalse(rec["executed"])
        self.assertIn("BLOCKED", rec["execution"])

    def test_cumulative_deny(self):
        ledger, hop, _ = ledger_with_hop()
        ni.gate_intent(ledger, hop, "worker", 25, intent(), now=NOW)
        rec = ni.gate_intent(ledger, hop, "worker", 20, intent(), now=NOW)
        self.assertEqual(rec["gate"]["code"], "OVER_BUDGET")

    def test_wrong_agent_denied(self):
        ledger, hop, _ = ledger_with_hop()
        rec = ni.gate_intent(ledger, hop, "intruder", 2, intent(), now=NOW)
        self.assertEqual(rec["gate"]["code"], "AGENT_MISMATCH")


class TestnetStatus(unittest.TestCase):
    def test_live_shape_via_fake_opener(self):
        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self):
                return json.dumps({"result": {
                    "chain_id": "testnet",
                    "sync_info": {"latest_block_height": 123456,
                                  "latest_block_hash": "abc"}}}).encode()
        out = ni.check_testnet_status(opener=lambda u, b, t: Resp())
        self.assertTrue(out["reachable"])
        self.assertEqual(out["chain_id"], "testnet")
        self.assertEqual(out["latest_block_height"], 123456)

    def test_failure_is_a_result_not_a_raise(self):
        def boom(url, body, timeout):
            raise ConnectionError("dns down")
        out = ni.check_testnet_status(opener=boom)
        self.assertFalse(out["reachable"])
        self.assertIn("ConnectionError", out["error"])


if __name__ == "__main__":
    unittest.main()
