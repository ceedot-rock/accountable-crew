# Accountable Agent Crew

A multi-agent workbench where agents are accountable by construction:
model-backed agents with Agent-Rider signed identities, hiring each other for
subtasks over the Rider rail; every payment bounded by a Warrant spend mandate;
every cross-agent action producing a CuNi exactness receipt anyone can verify.
Demo thesis: "trust me" multi-agent demos become provable ones.

Built for the **Open Agent Hackathon 2026** (genai.works, Oct 22–27, 2026;
submissions close Oct 27, 23:45 UTC). Plan:
`~/workspace/your_files/open-agent-hackathon-build-plan.md`. The same build is
the Meta Global AI Developer Hackathon entry (window Oct 26 – Nov 4) with the
model endpoint swapped when the Meta key lands.

## The five Day-1 answers (confirmed by Corey, 2026-10-22)

1. **Who is the user?** A solo operator running a crew of AI agents that spend
   money and take actions on their behalf.
2. **What is the problem?** Every multi-agent demo says "trust me": you cannot
   prove which agent did what, whether spend stayed within bounds, or that a
   result wasn't altered after the fact.
3. **What goes in?** A job description plus a Warrant spend mandate (who may
   spend what, on which tasks); agents holding Agent-Rider signed identities;
   model access for the agent loop.
4. **What comes out?** The finished job plus a verifiable trail: every
   cross-agent action carries a CuNi exactness receipt, every payment is
   checked against its mandate, and violations (overspend attempt, anonymous
   agent, tampered mandate) are blocked and shown.
5. **Why does this need an agent?** The work is genuinely delegated: agents
   hire each other for subtasks and pay under mandates. A single prompt can't
   demonstrate cross-agent accountability — the accountability only exists
   between autonomous parties.

## Architecture

```
            job description + Warrant mandate
                          │
                          ▼
   ┌─────────────┐   post/claim tasks    ┌─────────────┐
   │  agent-loop │ ────── Rider MCP ───▶ │  agent-loop │  (one per crew seat)
   │  (lead)     │ ◀────── DMs ───────── │  (worker)   │
   └──────┬──────┘                       └──────┬──────┘
          │ hire / pay                          │ deliver
          ▼                                     ▼
   ┌──────────────────────────────────────────────────┐
   │ mandate-gate — verify warrant, gate every spend  │
   │ receipts     — CuNi envelope on every action     │
   └──────────────────────────────────────────────────┘
                          │
                          ▼
   ┌──────────────────────────────────────────────────┐
   │ console — crew view · mandate/spend · receipts   │
   └──────────────────────────────────────────────────┘
```

## How the pieces connect (all interfaces verified 2026-10-22)

| This repo | Connects to | Interface |
|---|---|---|
| `agent-loop/` | Agent-Rider (live, agentrider.fly.dev) | MCP streamable HTTP at `https://agentrider.fly.dev/api/mcp` via `~/workspace/agent-rider/mcp_client.py` (`MCPClient.initialize/list_tools/call_tool`). 66 tools live, incl. `register`, `issue_rider`, `verify_rider`, `post_task`, `claim_task`, `submit_task`, `approve_task`, `send_direct_message`. Identity: ES256 rider JWT, `X-Agent-Rider` header (see `~/workspace/agent-rider/adapter-spec.md`). |
| `agent-loop/` | Model (provider seam) | Every model call goes through `agent-loop/providers.py`: `nemotron-direct` (NVIDIA Nemotron — the researcher lane's working route per Corey's 2026-10-22 ruling; NOT the Meterless engine) and `openrouter` configs, both OpenAI-compatible chat completions. **No key exists on this VM for either** — a model plan raises `ProviderNotConfigured` naming the missing env var, never a silent fake. A third config, `scripted`, is a deterministic non-model provider so the full pipeline is testable today. |
| `mandate-gate/` | Warrant | Python port `~/workspace/warrant-crossmint/warrant.py`: `issue_warrant`, `attenuate`, `verify_warrant`, `gate_check` (8/8 integration tests pass). Signed variant: `~/workspace/warrant-ucan/` TS (`issueSignedWarrant`, `attenuateSigned`, `verifySignedWarrant`; 17/17 tests pass; the Python port verifies its signed warrants). |
| `mandate-gate/` | Payments | In-platform hires settle via Rider task escrow (AGC). Paid HTTP endpoints via the live x402 rail `~/workspace/rider-x402/` (402 → `X-PAYMENT` → verified on-chain, Base USDC). Gate runs BEFORE either rail is touched. |
| `receipts/` | CuNi | `~/workspace/fabric-phase1/builds/receipts/cuni_envelope.py`: `assemble_envelope(tool_receipt, meta, issuer_priv, key_id, receipt_kind)`, `verify_envelope(env, …)` (corpus 20/20, milestone 12/12). Optional on-chain anchor: `~/workspace/gitfix/cunivers/anchoring/`. |
| `console/` | All of the above | Read-only views over the crew's task state (Rider MCP), mandate/spend state (mandate-gate), and the receipt log (receipts/). New build — Rider's own console (`~/workspace/agent-rider/console/index.html`) is a different surface. |

## Demo scope (frozen — exactly 3 scenarios)

1. Crew plans a job → agents hire/pay each other under mandates.
2. An agent attempts to overspend and is blocked, on camera.
3. Receipt trail shown and verified; anonymous agent rejected; tampered
   mandate refused.

## Status

**Core pipeline built and live-proven, 2026-10-22** (the plan's Fri–Sun
work, pulled forward under Corey's "do all that needs to be done"):

- Agent loop v1 (`agent-loop/agent_loop.py`): Rider seat identity
  (register → vaulted key → rider JWT), full hire-rail lifecycle,
  provider-abstracted `plan()`. Crew seats: crew-lead
  `78a632ae52351538`, crew-researcher `253c5afe8b141faa`.
- Mandate gate (`mandate-gate/gate.py`): Warrant port + cumulative-
  spend ledger; every decision (allow/deny) is receipted.
- Receipts (`receipts/receipts.py`): CuNi check-kind envelopes,
  inner-signed by the acting seat, whole-trail offline verify.
- x402 client (`mandate-gate/paid_call.py` + pure-Python `ethsig.py`):
  live 402 handshake verified; signatures pass the server's own
  verifier (interop test). **Payment execution is implemented but has
  not run** — no funded payer key is configured for the crew; the
  driver records that stage BLOCKED with the live terms, never faked.
- Deterministic driver (`agent-loop/driver.py`): Scenario 1 end-to-end
  on the live rail, twice, both runs exit 0 with 12/12 receipts
  verified (`runs/run-20261022T142601Z/`, `runs/run-20261022T142807Z/`).
- Tests: `tests/` — 67 unit tests, all passing
  (`python3 -m unittest discover -s tests`): the original 47 plus 20
  for the NEAR leg.
- **NEAR testnet leg built 2026-11-14** (`near-rail/`): NEAR Intents
  swap declarations + Chain Signatures derivation, mandate-gated
  before anything is built, dry-run only — no quote, no signature,
  no broadcast. Live testnet RPC probe verified reachable
  (chain_id=testnet, block 277,711,098 at 16:15 EST); demo receipt in
  `runs/near-testnet-dryrun-20261114T211519Z.json`. Submit as
  testnet-only, never as a live NEAR rail.
- **Zetaris: NOT integrated — resource wall.** Corey ruled the
  self-hosted Freemium Docker route; this VM has 7.9 GB RAM (FAQ
  recommends ≥16 GB) and no container runtime; the Fly sprite is
  ~15 GB, unreachable from here, and busy. The three research sources
  are prepared from real data in `sponsors/sources/`; no Zetaris
  query has run and nothing may claim one has.
- Console UI: not built yet (Mon Oct 26 slot in the plan).
- Nothing here is deployed; seat keys live in `.keys/`
  (0600, gitignored) and are never committed. Public repo:
  github.com/ceedot-rock/accountable-crew — NEAR Build Beyond
  Boundaries submission, Nov 14, 2026 (testnet-only leg).
