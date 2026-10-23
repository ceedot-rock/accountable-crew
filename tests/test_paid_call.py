#!/usr/bin/env python3
"""x402 client tests: terms parsing against a fixture shaped like the
real rider-x402 server response, binding-message exactness, RLP
vectors, and the no-key path (which must raise, never skip silently)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mandate-gate"))
import paid_call  # noqa: E402

# Mirrors rider-x402/server.py payment_requirements() output shape:
# `amount` (not maxAmountRequired), howto under extra, EVM rails first.
SERVER_402 = {
    "x402Version": 2,
    "error": "payment required",
    "accepts": [
        {"scheme": "txHash", "network": "base", "amount": "20000",
         "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
         "payTo": "0xPAYTO",
         "resource": "https://rider-x402.fly.dev/api/x402/pcc/info",
         "extra": {"paymentProof": "txHash",
                   "howto": "1) transfer >= 2c native USDC on Base ..."}},
        {"scheme": "txHash", "network": "polygon", "amount": "20000",
         "asset": "0x3c499c542cEF5E3811E1192ce70d8ccC03d5c3359",
         "payTo": "0xPAYTO",
         "resource": "https://rider-x402.fly.dev/api/x402/pcc/info",
         "extra": {"paymentProof": "txHash", "howto": "..."}},
    ],
}


class FakeResponse:
    status_code = 402
    text = "{}"

    def json(self):
        return SERVER_402


class Terms(unittest.TestCase):
    def test_parse_server_shape(self):
        with mock.patch.object(paid_call, "_post",
                               return_value=FakeResponse()):
            terms = paid_call.fetch_terms(paid_call.PCC_INFO_URL, {})
        self.assertEqual(terms["network"], "base")  # first EVM rail
        self.assertEqual(terms["amount_base_units"], 20000)
        self.assertEqual(paid_call.terms_price_cents(terms), 2)
        self.assertTrue(terms["howto"].startswith("1) transfer"))
        self.assertEqual(terms["resource"],
                         "https://rider-x402.fly.dev/api/x402/pcc/info")

    def test_non_402_is_an_error(self):
        r = FakeResponse()
        r.status_code = 200
        with mock.patch.object(paid_call, "_post", return_value=r):
            with self.assertRaises(paid_call.PaidCallError):
                paid_call.fetch_terms(paid_call.PCC_INFO_URL, {})

    def test_fractional_cent_terms_rejected(self):
        terms = {"amount_base_units": 20001}
        with self.assertRaises(paid_call.PaidCallError):
            paid_call.terms_price_cents(terms)


class BindingMessage(unittest.TestCase):
    def test_exact_server_format(self):
        msg = paid_call.binding_message(
            "0xABCDEF", "https://rider-x402.fly.dev/api/x402/pcc/info")
        self.assertEqual(
            msg,
            b"rider-x402 payment proof\ntxHash: 0xabcdef\n"
            b"resource: https://rider-x402.fly.dev/api/x402/pcc/info")


class Rlp(unittest.TestCase):
    def test_vectors(self):
        self.assertEqual(paid_call._rlp_encode(b"dog").hex(), "83646f67")
        self.assertEqual(paid_call._rlp_encode(1024).hex(), "820400")
        self.assertEqual(paid_call._rlp_encode([]).hex(), "c0")
        self.assertEqual(paid_call._rlp_encode(0).hex(), "80")
        self.assertEqual(paid_call._rlp_encode(b"").hex(), "80")


class NotFunded(unittest.TestCase):
    def test_no_key_raises_with_terms_attached(self):
        with mock.patch.object(paid_call, "_post",
                               return_value=FakeResponse()):
            with self.assertRaises(paid_call.PaidCallNotFunded) as cm:
                paid_call.paid_call(paid_call.PCC_INFO_URL, {}, None)
        self.assertEqual(cm.exception.terms["network"], "base")
        self.assertEqual(cm.exception.terms["amount_base_units"], 20000)


if __name__ == "__main__":
    unittest.main()
