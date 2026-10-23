# mandate-gate

The spend checkpoint. No crew payment — Rider task escrow or an x402
paid call — happens unless this gate approves it against the caller's
Warrant. Deny by default on any failure; every decision, allow and
deny alike, is reported to a callback so it can be receipted (the
denial receipts are half the demo).

**Built 2026-10-22 (the plan's Sat Oct 24 gate, pulled forward).**

## Files

- `gate.py` — mandate issue/attenuate wrappers + `MandateLedger`
  (cumulative-spend enforcement) over the verified Warrant port.
- `paid_call.py` — the x402 (txHash scheme) client for the live rail.
- `ethsig.py` — pure-Python Keccak-256 / secp256k1 / EIP-191 (this VM
  has no eth libraries); pinned by known-answer tests, and its
  signatures verify under the x402 server's own verifier (interop
  test in `../tests/test_ethsig.py`).

## Two enforcement layers (the scaffold TODO, resolved)

- `warrant.gate_check` (port at `~/workspace/warrant-crossmint/
  warrant.py`, 8/8 tests) is stateless: caller == effective last hop,
  single cost ≤ cap, not expired. Deny codes verbatim:
  `WARRANT_DENIED | WARRANT_EXPIRED | OVER_BUDGET | AGENT_MISMATCH`.
- `MandateLedger` (here) adds the missing half: cumulative spend per
  warrant document (keyed by a SHA-256 fingerprint of the canonical
  warrant JSON). A spend that would push the running total over the
  cap is denied `OVER_BUDGET` even when the call alone would pass;
  denied spends are never booked. Every decision goes to the
  `on_decision` callback as a receipt-ready record.

Attenuation is the port's own: hops may only narrow (100¢ → 40¢ → 15¢
in the demo chain); a widening attempt raises `WarrantError` — that
exception is the tamper signal and callers must let it surface.

## paid_call.py — x402 client (live-verified handshake)

Implements the client handshake from
`~/workspace/custom-skills/x402-api-client/SKILL.md` against
rider-x402.fly.dev: unpaid POST → parse the real 402 terms (the
server's `accepts[]` uses `amount`, howto under `extra`) → ERC-20
USDC transfer to `payTo` → sign the server's exact binding message
(`rider-x402 payment proof\ntxHash: <lowercase>\nresource: <url>` —
mirrors `rider-x402/ethsig.py binding_message`, NOT the howto
template verbatim) → retry with the `X-PAYMENT` proof header.
Terms are fetched fresh on every call; one payment pays for one call.

**Payment execution status:** the full execution path is implemented
and unit-tested (terms parsing, binding message, RLP vectors,
signature interop), and the live 402 handshake runs in the driver.
An actual on-chain payment has **not** been executed by the crew:
no funded payer key is configured (`CREW_X402_PAYER_KEY` unset), and
the server's lab free-use pass keys off a `LAB_WALLETS` allowlist
whose wallet key is Corey's custody. Without a key, `paid_call()`
raises `PaidCallNotFunded` carrying the live terms — the driver
receipts that as a BLOCKED stage, never as a payment.
