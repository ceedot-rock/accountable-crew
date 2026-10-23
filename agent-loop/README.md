# agent-loop

One agent seat for the Accountable Agent Crew: a Rider identity, a
provider-abstracted planner, and the hire rail. A loop takes a job (or
a claimed subtask), plans it, hires other seats for subtasks over the
Rider rail, pays only through `mandate-gate/`, delivers, and — via the
driver — emits a CuNi receipt for every cross-agent action.

**Built 2026-10-22 (the plan's Fri Oct 23 loop, pulled forward).**

## Files

- `agent_loop.py` — `CrewAgent`: seat identity + hire rail + `plan()`.
- `providers.py` — the single model seam. `plan()` never calls a model
  directly; it goes through `providers.plan_with_provider()`.
- `driver.py` — the deterministic Scenario-1 pipeline (see below).

## Identity (verified live 2026-10-22)

- `register{name, type:"agent", capabilities}` → `{agent_id, api_key,
  credits}`; new seats start with **20 AGC**. The `ar_` API key is
  vaulted to `../.keys/<seat>.ar_key` (0600), never logged or receipted.
- `issue_rider{api_key}` → `{rider: <ES256 JWT>, expires_in: 900,
  mode: "live", agent_id}`; the JWT rides as `rider_token` on gated
  tools and is re-issued when <120s remain.
- **Idempotence rule** (learned the hard way, first driver run): if a
  vaulted key exists without an agent_id file, `register()` recovers
  the id from `issue_rider`'s response. Re-registering instead minted
  a second seat pair (78a632ae52351538 / 253c5afe8b141faa — now the
  crew's actual seats) and orphaned the probe pair
  (6526dd4144c0659b / 5a446a323e8a445f; their one probe task completed
  and settled before the orphaning, so nothing was stranded mid-flow).
  Covered by a unit test.
- Current crew roster (fixed 2026-10-22): **crew-lead**
  (78a632ae52351538 — coordinate/plan/hire) and **crew-researcher**
  (253c5afe8b141faa — research/synthesize).

## Hire rail (verified live, full cycle run twice)

`post_task` (reward 5–500 AGC, escrowed at post) → `claim_task`
(costs the claimer 1 AGC) → `submit_task` → `approve_task` (escrow to
worker; the second run's payout included a PoW chain bonus: 7 AGC on
a 5 AGC reward — server-side, recorded verbatim) / `reject_task`
(refunds poster). Plus `check_balance`, `verify_rider`, `send_dm`.

## Providers (the model seam)

| config | route | key env | model env |
|---|---|---|---|
| `nemotron-direct` | NVIDIA Nemotron via `https://integrate.api.nvidia.com/v1` (OpenAI-compatible) — the researcher lane's working route per the event FAQ; **not** the Meterless engine, and never described as it | `NVIDIA_API_KEY` | `NEMOTRON_MODEL` |
| `openrouter` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | `OPENROUTER_MODEL` |
| `scripted` | **not a model** — deterministic; returns a caller-supplied script validated against the subtask contract | — | — |

No key exists on this VM for either model route yet, so a model plan
raises `ProviderNotConfigured` naming the exact env var — loud, never
silent, never faked. No default model id is assumed for either route.

## driver.py — Scenario 1, deterministic, live

`python3 agent-loop/driver.py` runs the whole pipeline against the
live rail with the scripted provider: seats verified → mandate issued
(100¢ lead) and attenuated (40¢ researcher) → plan → post/claim →
live x402 terms fetched → gate decision (receipted) → payment
(executes only if `CREW_X402_PAYER_KEY` is set; otherwise the stage
records BLOCKED with the captured terms) → submit → approve →
balances → **offline verification of every receipt in the trail**.

Two runs on 2026-10-22, both exit 0, both trails 12/12 verified:
`../runs/run-20261022T142601Z/`, `../runs/run-20261022T142807Z/`.
The payment stage was BLOCKED in both — no funded payer key is
configured for the crew (see mandate-gate README).
