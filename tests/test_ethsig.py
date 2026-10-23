#!/usr/bin/env python3
"""Known-answer + interop tests for mandate-gate/ethsig.py."""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mandate-gate"))
import ethsig  # noqa: E402


class KeccakKAT(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(
            ethsig.keccak256(b"").hex(),
            "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")

    def test_abc(self):
        self.assertEqual(
            ethsig.keccak256(b"abc").hex(),
            "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")

    def test_long_input_multiblock(self):
        # 200 bytes > 136-byte rate: exercises multi-block absorption.
        data = b"a" * 200
        self.assertEqual(len(ethsig.keccak256(data)), 32)
        self.assertNotEqual(ethsig.keccak256(data), ethsig.keccak256(b"a" * 199))


class AddressKAT(unittest.TestCase):
    def test_privkey_one(self):
        self.assertEqual(ethsig.privkey_to_address(1).lower(),
                         "0x7e5f4552091a69125d5dfcb7b8c2659029395bdf")


class PersonalSign(unittest.TestCase):
    def test_recover_roundtrip_and_determinism(self):
        msg = b"rider-x402 payment proof\ntxHash: 0xabc\nresource: https://x"
        sig1 = ethsig.personal_sign(1, msg)
        sig2 = ethsig.personal_sign(1, msg)
        self.assertEqual(sig1, sig2)  # RFC 6979 deterministic
        raw = bytes.fromhex(sig1[2:])
        self.assertEqual(len(raw), 65)
        r = int.from_bytes(raw[:32], "big")
        s = int.from_bytes(raw[32:64], "big")
        v = raw[64]
        self.assertLessEqual(s, ethsig._N // 2)  # low-s
        rec = ethsig.recover_address(ethsig.eip191_hash(msg), v, r, s)
        self.assertEqual(rec.lower(), ethsig.privkey_to_address(1).lower())

    def test_wrong_message_recovers_other_address(self):
        sig = ethsig.personal_sign(1, b"message A")
        raw = bytes.fromhex(sig[2:])
        r = int.from_bytes(raw[:32], "big")
        s = int.from_bytes(raw[32:64], "big")
        rec = ethsig.recover_address(ethsig.eip191_hash(b"message B"),
                                     raw[64], r, s)
        self.assertNotEqual(rec.lower(), ethsig.privkey_to_address(1).lower())


class ServerInterop(unittest.TestCase):
    """My signatures must verify under the x402 server's OWN verifier
    (~/workspace/rider-x402/ethsig.py verify_personal_sign)."""

    def test_server_verifier_accepts_my_signature(self):
        spec = importlib.util.spec_from_file_location(
            "server_ethsig",
            str(Path.home() / "workspace" / "rider-x402" / "ethsig.py"))
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as e:  # server module deps unavailable here
            self.skipTest(f"server ethsig not importable: {e}")
        msg = ("rider-x402 payment proof\ntxHash: 0x" + "ab" * 32 +
               "\nresource: https://rider-x402.fly.dev/api/x402/pcc/info"
               ).encode()
        sig = ethsig.personal_sign(1, msg)
        signer = mod.verify_personal_sign(msg, sig)
        self.assertIsNotNone(signer)
        self.assertEqual("0x" + signer.hex(),
                         ethsig.privkey_to_address(1).lower())


if __name__ == "__main__":
    unittest.main()
