# Zetaris image-access DEEP DIVE — 2026-10-22 (follow-up to image-access-probe-2026-10-22.md)

Corey directed a deeper investigation ("do a deep dive on this issue
and fix"). Verdict: **the block is organizer-side and now proven at the
token layer.** The event ACR credential authenticates, but every access
token it can obtain carries **zero grants** — for every repository name
with any documentary basis (100+ names tried across both probes, plus
wildcards, plus the catalog). No Zetaris container was started, no
source registered, and **no Zetaris query has run**. The zetaris-crew
sandbox was never started during this run and remains stopped
(verified via `sbx --cloud ls`).

## Avenue A — token forensics (the decisive evidence)

Decoded the JWT payloads of access tokens issued by
`https://zetarishackathon.azurecr.io/oauth2/token` in four exchanges:
POST password grant with **no scope**, POST with `registry:catalog:*`,
POST with `repository:zetaris/lightning-server:pull`, and GET with
basic auth + no scope (the docker-login challenge flow). All four
returned valid RS256 JWTs with identical claim structure:

- `iss`: "Azure Container Registry" · `aud`:
  `zetarishackathon.azurecr.io` · `sub`: the token username ·
  `version`: "2.0" · `grant_type`: "access_token" · a constant `rid`
  across exchanges.
- **`access`: [] and `roles`: [] in every token — including the
  no-scope exchange.**

ACR issues access = (token's scope map) ∩ (requested scopes). An empty
result for a *requested* scope proves that scope is not in the map.
Across both probes the map provably contains **none** of: the catalog
grant, or pull / metadata_read / content-read on any of 100+ candidate
repositories (below). The only names that could still theoretically be
in the map are names never requested — and every name with a public or
documentary basis has now been requested. Name-guessing is exhausted;
this is a scope-map state, not a naming puzzle.

What the token CAN do: authenticate (`docker login` succeeds; the
token endpoint issues JWTs). What it CANNOT do: pull, read metadata,
or list the catalog for any probed repository — i.e., everything a
participant needs.

## Avenue B — name discovery (no new names exist in public sources)

- Web search for the literal host `zetarishackathon.azurecr.io` and
  for participant pull commands: **no public page quotes them.**
- Fresh clone of zetaris/Freemium (commit 9dd4fe9), full-tree grep for
  `azurecr|ghcr|registry|docker login|image:`: the ONLY image
  references anywhere are the compose's Docker Hub names
  (`zetaris/lightning-server|lightning-api|lightning-gui:v2.4.1.0-latest`,
  plus privateai/genz-mcp/ollama-models/digivatar). No hackathon
  folder, no alternate registry, no ACR mention. (The README heading
  "Login to azure docker repo" sits over a plain `docker login` —
  Docker Hub.)
- Zetaris KB (kbase.zetaris.com): full sitemap enumerated — 233
  articles, **no hackathon or freemium article**. The one install
  article ("Docker Desktop installation using images distributed via
  Docker hub") documents Zetaris's own distribution model: images on
  Docker Hub, and — verbatim — "**Your access to the zetaris docker
  containers will be activated within 24 hours of request**", i.e.
  per-Docker-Hub-account grants issued by Zetaris on request.
- The public Open Agent Hackathon event page contains no setup,
  docker, or registry content; sponsor-tech specifics live only in the
  gated HackOS/academy lessons (Corey's participant login — outside
  this run's reach, as before).

## Avenue C — scope-map probing (completed space)

This run scope-checked **77 additional repository names** (each with
pull + metadata_read + content/read in one token request) plus the
first probe's ~55 names and daemon manifest/pull checks, plus
wildcards `repository:*:pull`, `repository:zetaris/*:pull`,
`repository:*:metadata_read`. Families covered: compose-exact
(zetaris/lightning-server, -api, -gui, privateai, genz-mcp,
ollama-models, digivatar), bare lightning-*, lightning/*, vendor-flat
(zetaris, zetaris-*, zetaris-lightning*), hackathon families
(hackathon/*, zetaris-hackathon/*, hackathon2026, hackathon-2026,
openagenthackathon/*, open-agent-hackathon/*, genai/*, genaiworks),
registry-label prefixes (zetarishackathon/*), trial names
(zetaristrial/*, trial/* — from Zetaris's own Azure footprint),
product names (freemium/*, ndp/*, harness, data-harness,
ai-data-harness), and single names (participants, images, team,
shared, public, release, server, api, gui, v2.4.1.0). **Result: 0
non-empty `access` arrays. Untried space = names with zero documentary
or public basis.**

## Avenue D — alternate distribution (both dead)

- **GHCR**: anonymous token issuance for ghcr.io/zetaris/{lightning-
  server, lightning, zetaris, freemium} is refused (UNAUTHORIZED at
  the token endpoint) — no public GHCR packages exist under those
  names, and no source names GHCR as a Zetaris channel.
- **Build from source**: impossible. The Freemium repo contains **no
  Dockerfile for lightning-server, lightning-api, or lightning-gui**
  (the only Dockerfile is a Spark sidecar; the repo ships start
  scripts and config only). The Lightning binaries exist solely as
  prebuilt private images.
- Docker Hub (probe 1): the three core repos are private; the org's
  5 public repos don't include them.

## Bonus find for stand-up day (from the Freemium repo's sample data)

`lightning/data/1d0c220d/users/dev@account.com/history` records the
real registration dialect, so source registration is pre-mapped if
images ever run: `CREATE DATASOURCE <name> ... OPTIONS (jdbcdriver,
jdbcurl, username, schema, password)` then `REGISTER DATASOURCE
TABLES FROM <name>;` for JDBC sources, and `CREATE LIGHTNING FILESTORE
TABLE <t> FROM FILEDB FORMAT <PARQUET|CSV> OPTIONS (PATH '...',
header 'true', inferSchema 'true')` for file sources (our three CSVs).

## The unblock — either route, both organizer-side

**(a) Fix the ACR scope map** (paste-ready for the event team):
"Token `zethackuser91b775030eea47d1886bbf7c2d786f55` on
zetarishackathon.azurecr.io authenticates, but its scope map grants
nothing: every token exchange returns `access: []` — including for
repository:zetaris/lightning-server:pull and registry:catalog:*.
Please bind a scope map to this token granting pull + metadata_read
on the hackathon image repositories (expected:
zetaris/lightning-server, zetaris/lightning-api, zetaris/lightning-gui
at tag v2.4.1.0-latest) — or send the exact repository names if they
differ, scoped to this token."

**(b) Docker Hub grant** (Zetaris's own documented model): Zetaris
activates pull access per Docker Hub account on request (KB: "within
24 hours of request"). This route needs the lab's Docker Hub account
name sent to Zetaris/the organizers and their activation — no such
grant exists today.

Once either lands, completion is mechanical in the already-provisioned
sandbox (stopped; registry login + postgres:15.1 cached): pull → core
compose up → dev-account.sh admin → register the three sources
(dialect above) → the designed three-way federated query → evidence
saved here.
