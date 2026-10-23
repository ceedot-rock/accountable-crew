# sponsors/sources — the three research sources, prepared for Zetaris

These are the three small **real** sources the Zetaris federated query
is designed to join in place (see ../README.md). They are prepared and
verified; they are **not yet registered in any Zetaris instance**,
because no instance exists yet — see the stand-up attempt below.
Nothing in this directory claims a Zetaris integration has run.

- `catalog.csv` — the rider-x402 product/price catalog, transcribed
  from the live server's own PRODUCTS table
  (`~/workspace/rider-x402/server.py`, read 2026-10-22). 15 rows.
- `rider_tasks_export.csv` — real tasks from the live Agent-Rider
  rail, fetched via the unauthenticated `get_task` MCP tool on
  2026-10-22. All three are crew end-to-end runs, status `completed`.
  (The first row's poster seat, 6526dd4144c0659b, was the probe seat
  orphaned by the first driver run's re-registration bug — see
  agent-loop README. The task and its settlement are real regardless.)
- `spend_ledger.csv` — the current crew seats' AGC movements, every
  row taken from an observed live balance or approve_task response
  during the two driver runs of 2026-10-22. Balances reconcile:
  lead 20 → 15 → 10; researcher 20 → 19 → 24 → 23 → 30.

The federated query this is designed for (to run the day an instance
exists): *"Which completed crew tasks paid for PCC information, what
did the information cost in cents, and what did the worker net in
AGC?"* — a three-way join across tasks, catalog, and ledger.

## Stand-up, 2026-10-22 — host solved, image access blocked

First attempt hit a resource wall on this build VM (7,936 MB RAM, no
container runtime). Corey then ruled "do it on docker": a Docker Cloud
sandbox **zetaris-crew** (shape large: 8 vCPU / 16,384 MiB; Docker
Engine 29.9.2; Compose v5.6.1) was provisioned and the Freemium repo
cloned inside it — the host problem is solved, and the sandbox is left
created-but-stopped with the postgres image cached. Deployment is now
blocked purely on **image acquisition**: the event ACR credential
(zetarishackathon.azurecr.io) authenticates but grants no pullable
repository discoverable from outside, and the Docker Hub
zetaris/lightning-* images are private. Full evidence:
`../zetaris-evidence/image-access-probe-2026-10-22.md` and the
"Stand-up" section of `../README.md`.

**What unblocks it:** the exact ACR image references from the event's
participant materials (or a scope-map fix by the event team), or
Docker Hub pull access to the private zetaris/* repos. Until an
instance is actually up, `zetaris_client.py` stays a stub over the
documented REST flow with endpoint paths as explicit TODOs, and no
demo material may claim a Zetaris query ran. Registration of the
three sources above is a mechanical ~1h step once an instance is up;
the sources are ready.
