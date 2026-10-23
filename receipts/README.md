# receipts

A CuNi exactness receipt on every cross-agent action: hire, gate
decision, payment (or its blockage), delivery, denial. The trail is
demo scenario 3 — it verifies offline, with no lab server, from the
envelope file + the issuer's public key alone.

**Built 2026-10-22 (the plan's Sun Oct 25 receipts, pulled forward).**

## Crew conventions (fixed at build time)

- **Kind: `"check"`**, not the envelope default `"audit"`. In
  `cuni_envelope`, audit-kind semantics demand code-audit artifacts
  (law/impl hash recomputation); crew action records are check-kind:
  a named signer attests the record, the envelope binds it.
- **Two signatures, two claims.** Each action record is *inner-signed*
  by the acting seat's own Ed25519 key (`sign_action()` adds
  `signer_pubkey` + `signature` over cuni_envelope's canonical bytes;
  the envelope refuses unsigned inner receipts). The trail issuer key
  signs the outer envelope: the seat attests "I did this", the issuer
  attests "this record is in the trail".
- **Seat Ed25519 keys are local action-signing keys** (`../.keys/
  <seat>-ed.key`, 0600), distinct from Rider identity (the ES256 JWT
  layer). Each record body carries the seat's Rider `agent_id` so the
  layers cross-check.
- **Meta set** (cuni_envelope REQUIRED_META_FIELDS, read from source):
  `audit_id` = `accountable-crew/<run-id>`; `issued_at` UTC;
  `issuer.auditor_did` = `did:agent-rider:<lead agent_id>`;
  `target` / `property` / `property_ref` state only what is true of
  this local build (see `receipts.py` DEFAULT_* constants).
- **No floats** — canonical bytes reject them; `_canon_safe()` coerces
  at record time (integral floats → int, others → str).

## API

- `CrewTrail(path, issuer_priv, key_id, audit_id, issuer_did)` —
  `.emit(action, signer_priv)` signs, envelopes, appends one JSONL
  line; sequence numbers continue across appends.
- `ensure_keypair(keys_dir, name)` — load-or-generate `<name>.key`
  (0600) / `<name>.pub`; refuses to overwrite.
- `verify_trail(path, issuer_pubkey)` — one result dict per line,
  never raises; a tampered line comes back
  `{"ok": False, "error": "TAMPERRED_INNER", ...}` (proven in tests:
  editing a receipted cost after the fact fails exactly that line,
  neighbours still verify).

## Evidence

Driver runs 2026-10-22: `../runs/run-20261022T142601Z/trail.jsonl`
and `../runs/run-20261022T142807Z/trail.jsonl` — 12 receipts each,
**12/12 verified offline** at the end of each run.

Underlying implementation: `~/workspace/fabric-phase1/builds/
receipts/cuni_envelope.py` (corpus 20/20, milestone 12/12,
2026-10-22). Optional on-chain anchoring of a trail via
`~/workspace/gitfix/cunivers/anchoring/` exists (used for ExactOdds)
but is not wired into the crew yet.

## Sponsor touch-point (pending Zetaris)

When the researcher lane's Zetaris query exists, its receipt will
bind the exact SQL text + a SHA-256 of the exact result rows — the
fields will be added to the action record then, from the real query,
not invented now. Blocked on a Zetaris instance; see
`../sponsors/sources/README.md` for the stand-up attempt.
