# near-rail/ — NEAR testnet payment leg

Built 2026-11-14 for the NEAR Build Beyond Boundaries hackathon
(closes Nov 14, 23:59 UTC). **Testnet dry-run only** — see the honesty
box at the bottom before citing anything here.

## What it is

The crew's third payment rail, next to Rider task escrow (AGC) and
the x402 rail. An agent payment is expressed as a **NEAR Intents**
swap declaration (`token_diff`: what goes in, what is expected out),
gated by the Warrant mandate first, and signable for other chains via
**Chain Signatures** (NEAR MPC contract signs a 32-byte payload hash
under a derivation path — the agent never holds the key).

## Do X, see Y

```sh
cd accountable-crew
python3 near-rail/demo_testnet.py
# gate: ALLOW (remaining 38c)
# testnet rpc: reachable=True chain_id=testnet block=<height>
# chain signatures: NOT_SIGNED
# receipt: runs/near-testnet-dryrun-<ts>.json
```

Inspect the receipt: the intent object, the gate decision, the live
testnet RPC status (read-only `status` call), and the exact Chain
Signatures request that was **not** sent.

```sh
python3 -m unittest discover -s tests   # 47 existing + 12 NEAR tests
```

## Files

- `near_intents.py` — stdlib-only leg: `build_intent`,
  `intent_payload_hash`, `chain_signature_derivation_path`,
  `chain_signature_request`, `check_testnet_status`, `gate_intent`.
- `demo_testnet.py` — the dry-run driver; writes one receipt JSON
  per run under `runs/`.
- `README.md` — this file.

## How the gate composes

Every intent goes through `mandate-gate/gate.py` (`MandateLedger`)
BEFORE it becomes an executable request — same rule as the Rider and
x402 rails. A denied intent returns `executed: False` and no
signature request is ever built for it. Deny by default.

## Honesty box — read before submitting or demoing

- **No solver quote has been fetched.** The intent carries no
  guaranteed out-amount; `min_amount_out` is the caller's floor.
- **No signature has been produced.** No MPC contract is configured
  on this machine (`NEAR_MPC_CONTRACT` unset) and no funded NEAR key
  exists here; `chain_signature_request` raises `NearNotConfigured`
  carrying the exact request that was not sent.
- **Nothing has been broadcast or settled** on testnet or mainnet.
  The only live-network call is a read-only RPC `status` probe.
- **Asset ids and amounts in the demo are illustrative dry-run
  values** (`wrap.testnet` -> `usdc.fakes.testnet`, 1,000,000 base
  units, cost 2c against a 40c mandate). They assert no live token
  deployment and move no tokens.
- **Payout account** for the submission form: Corey's NEAR account
  `7cdb35e939ee4e51a7b47f8b411335ea683f7ec6285f4e73a1e35ad9b902719d`
  (64-hex implicit account; same id on testnet and mainnet).
  Supplied by Corey 2026-11-14.

The submission form must describe this leg as **testnet-only /
dry-run**, never as a live NEAR rail.
