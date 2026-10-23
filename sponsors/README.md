# sponsors

Sponsor integrations for the Open Agent Hackathon 2026. Rules 06 makes
these **mandatory for every submission**: Zetaris integrated in the
product (6.1/6.2/6.4), the product running on NVIDIA Nemotron directly or
through the Meterless engine (event FAQ), plus a written sponsor
explanation (6.4). Design rule: claims match evidence — each integration
does real work in the demo workflow or it doesn't ship.

Full design + costing: `~/workspace/your_files/open-agent-hackathon-build-plan.md`
("Sponsor integration" section). Build slots: Fri Oct 23 (stand-up +
hello-worlds), Sun Oct 25 (Zetaris wired into the research subtask).

## Zetaris — data layer (federated query)

**Role in the Crew:** the researcher agent answers a question from the
lab's own fragmented records by issuing ONE federated SQL query through
Zetaris, joining three small real sources in place: (1) the rider-x402
product/price catalog (SQLite/CSV), (2) a Rider task/escrow export
(CSV/JSON), (3) the crew spend ledger (CSV). Returned rows are the
evidence behind the crew's answer; the research receipt (see
`../receipts/`) binds the query text + a hash of the exact result set.

**Verified interface** (official knowledge base, kbase.zetaris.com,
"Accessing Zetaris through Rest API", read 2026-10-22):

- Login → returns `idToken` (bearer, used for authorization on later
  calls) + `refreshToken` (regenerates the idToken).
- `OpenSqlQuery`: body `{"select": "<SQL>", "pageLimit": N}`, pageLimit
  range 1–100. Response carries the result rows + a `queryToken`.
- `PageSqlQuery`: paginate using the `queryToken`.
- `CloseSqlQuery`: release the cached query server-side (200 = closed).
- Requests carry a `requestId` UUID header (per the documented env vars).
- The instance base URL is the user's own API URI (their Zetaris
  instance), not a single global endpoint.

`zetaris_client.py` in this directory is a stub over exactly this flow —
no more of the API is claimed than the page documents.

**Stand-up, 2026-10-22 — host SOLVED, image access BLOCKED** (full
evidence in `zetaris-evidence/`): the earlier resource wall (this build
VM: 7,936 MB RAM, no container runtime) was bypassed per Corey's
"do it on docker" ruling: a Docker Cloud sandbox named
**zetaris-crew**, shape **large (8 vCPU / 16,384 MiB)**, was created on
Corey's Docker account. Verified inside it: 15 GiB free RAM, Docker
Engine 29.9.2 (daemon running), Docker Compose v5.6.1. The Freemium
repo was cloned in the box (commit in
`zetaris-evidence/freemium-git-commit.txt`; compose copy alongside it).
The sandbox is left **created-but-stopped** (registry login + the
postgres:15.1 image cached) for reuse during hackathon week.

What blocks deployment is image acquisition — both routes:

- **Event ACR** (`zetarishackathon.azurecr.io`, credentials vaulted at
  `~/.config/crew-secrets/zetaris_acr.env` on the build VM, never
  logged): `docker login` **succeeds** from the sandbox and the stored
  credential hash-matches the vault file; the registry's
  WWW-Authenticate challenge (realm …/oauth2/token, service = registry
  host) was verified. But the token's granted `access` is **empty** for
  every repository/action probed (~55 names × pull / metadata_read /
  content-read action vocabularies, GET and POST grants, plus the
  daemon's own manifest/pull flow); `/v2/_catalog` is denied. So the
  registry has no image this credential can pull that is discoverable
  from outside — the exact image references presumably live in the
  event's participant materials (HackOS/academy quick-start, behind
  the participant login). Probe record:
  `zetaris-evidence/image-access-probe-2026-10-22.md`.
- **Docker Hub** (the Freemium GitHub route): `postgres:15.1` pulled
  fine; `zetaris/lightning-server`, `zetaris/lightning-api`,
  `zetaris/lightning-gui` are **private** ("pull access denied"; the
  Hub API returns "object not found" anonymously, and the org's 5
  public repos don't include them). Deployment via this route needs a
  Docker Hub login with Zetaris-granted pull access — not available.

So: no Zetaris container has started, the three sources in `sources/`
are **not registered** anywhere yet, and **no Zetaris query has run**.
No material may claim otherwise. Unblock = the exact ACR image
references from the participant materials (or a scope-map fix by the
event team), or Docker Hub pull access to the private zetaris/*
repos. Once an image source works, stand-up is the documented
compose flow (`docker compose pull` / `up`, then add the admin user
via `dev-account.sh`) in the already-provisioned sandbox.

**Deep dive, 2026-10-22 (later)** —
`zetaris-evidence/image-access-deep-dive-2026-10-22.md`: the block is
now proven at the token layer, which retires the "wrong image name"
theory. Decoded JWTs from the ACR token endpoint (no-scope, catalog,
repo-pull, and docker-login flows) all carry **`access: []` and
`roles: []`** — the token's scope map grants nothing for anything
requested. Name discovery was exhausted: 100+ candidate repositories
scope-checked across both probes (compose-exact, hackathon/event
slugs, registry-label prefixes, wildcards) with 0 grants; the
Freemium repo (full-tree grep), the full Zetaris KB sitemap (233
articles, no hackathon/freemium article), and public web search
contain no other image names or pull commands. GHCR has no public
zetaris packages, and building from source is impossible (Freemium
ships no Dockerfile for server/api/gui — the binaries exist only as
prebuilt private images). Zetaris's own documented distribution model
(KB) is Docker Hub with per-account access "activated within 24 hours
of request". The unblock is therefore one of two organizer-side
actions, both specified paste-ready in the deep-dive file: (a) bind a
non-empty scope map to our ACR token (or name the exact repositories
it is scoped to), or (b) a Docker Hub pull grant for the lab's
account. The sandbox remains stopped with login + postgres cached;
completion (pull → compose up → register sources → federated query)
is mechanical the moment either lands.

**Missing evidence (TODOs):**

- **Instance**: none running yet (image access, above). Sandbox host
  is ready.
- **Exact REST endpoint paths**: the knowledge base documents the
  Postman-collection flow (folder/request names), not raw URL paths.
  Pull the paths from the official Postman collection once an account/
  instance exists; do not guess them in code.
- **Source registration steps** for SQLite/CSV/JSON sources in the cloud
  UI vs the Freemium GUI — unverified until an instance is up.
- Which SQL dialect the federated query targets (Spark/Presto/Trino
  engine underneath) — confirm with a trivial query at stand-up.

## Meterless — power layer (NVIDIA Nemotron inference)

**Role in the Crew:** route ONE real lane's inference to a Nemotron
model — the researcher agent, whose job is synthesis over the Zetaris
evidence ("right model in each lane" is the event's own framing).

**Route decision (Corey, 2026-10-22 — "do all that needs to be
done"):** the working route is **Nemotron direct**, the FAQ-sanctioned
fallback, implemented as the `nemotron-direct` provider config in
`../agent-loop/providers.py` (NVIDIA's OpenAI-compatible API;
`NVIDIA_API_KEY` + `NEMOTRON_MODEL`). The Meterless-engine route stays
a TODO until the participant-login details land. **No material may
claim Meterless-engine use** — the writeup names the route that
actually ran, which for now is Nemotron direct. Neither an NVIDIA key
nor a model id exists on this VM yet, so the lane currently raises a
loud `ProviderNotConfigured`; it has not served a call.

**Verified** (official event materials only — academy.genai.works course
page + FAQ, read 2026-10-22): product names are "Meterless Nightshift"
("run your product through Meterless Nightshift on NVIDIA Nemotron") and
"Meterless Engines" (Build Day, with Cursor); "Your product runs on
NVIDIA Nemotron, either connected directly or through the Meterless
engine."

**Missing evidence (TODOs) — larger than Zetaris's:**

- **No official Meterless site or public API docs found** in search on
  2026-10-22. Endpoint shape, auth, model IDs, and OpenAI-compatibility
  are all UNVERIFIED. Do not write a client stub until the real interface
  is in hand — there is deliberately no `meterless_client.py` here.
- Access specifics live in the event's **Power Quick Start** lesson
  behind the participant (academy/HackOS) login — account creation is
  Corey's identity step.
- The "API metering / pay-per-use" characterization in earlier lab notes
  is **unconfirmed by any official source** — never repeat it in the
  writeup or deck. If the product does expose usage metering, that's a
  bonus to document once seen, not a design assumption.
- Whether the engine bills/limits by key, and any rate limits that would
  shape the demo's call pattern — check at hello-world time.

## NVIDIA (for the 6.4 writeup)

Contribution to name: Nemotron (via Meterless, or direct) produces the
researcher lane's evidence-backed synthesis — the answer the Track 02
demo is judged on. Claim only the model + route that actually ran in the
final build.

## Cursor (6.4 also asks)

Event materials say teams must use Cursor for development. The lab build
runs on Claude-based tooling. Either a genuine Cursor pass happens during
the build (console UI work is the natural slot) or the writeup has a
known gap — never claim Cursor use that didn't happen. Corey's call;
tracked in the plan.
