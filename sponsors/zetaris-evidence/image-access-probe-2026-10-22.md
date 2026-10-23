# Zetaris image-access probe — 2026-10-22 (in sandbox shell/zetaris-crew)

Outcome: **BLOCKED at image acquisition.** The sandbox host problem is
solved (see sandbox-and-docker.txt); neither image source yields the
Zetaris Lightning images with the credentials available. No Zetaris
container was started, no source was registered, and **no Zetaris
query has run**.

## Route A — event ACR (zetarishackathon.azurecr.io)

Credentials: event-issued, vaulted at ~/.config/crew-secrets/zetaris_acr.env
on the build VM (values never logged). Copied into the sandbox,
`docker login <registry> -u <user> --password-stdin` → **Login Succeeded**;
copied env file deleted inside the sandbox. Stored docker credential
hash-verified identical to the vault file.

- WWW-Authenticate challenge verified: realm
  `https://zetarishackathon.azurecr.io/oauth2/token`, service
  `zetarishackathon.azurecr.io`, catalog scope `registry:catalog:*`.
- `GET /v2/_catalog` (basic auth and catalog-scoped bearer) →
  UNAUTHORIZED / denied.
- Token exchange (GET query-param form and POST password-grant form)
  returns valid ACR JWTs whose `access` array is **empty** for every
  scope requested, including: `repository:zetaris/lightning-server:pull`,
  `...:content/read`, `...:metadata_read`, wildcard name/action forms,
  `registry:catalog:*`, and no-scope. ~55 repository names probed across
  batches (zetaris/*, lightning-*, hackathon/*, freemium, ndp, harness
  variants, etc.).
- `docker manifest inspect` (the daemon's own token flow) for
  zetaris/lightning-server, lightning-api, lightning-gui, freemium,
  ndp, zetaris, and prefixed variants × tags {latest, v2.4.1.0-latest,
  v2.4.1.0, 2.4.1.0} → all "denied" (never "manifest unknown", which
  would indicate a granted repo with a wrong tag).
- `docker pull zetarishackathon.azurecr.io/zetaris/lightning-server:v2.4.1.0-latest`
  → pull access denied.

Interpretation: the credential authenticates, but its scope map grants
no pullable repository discoverable from outside. The exact image
references presumably live in the event's participant materials
(HackOS/academy Zetaris quick-start, behind the participant login).
With a confirmed `repository:tag`, one `docker pull` inside this
sandbox tests it immediately — the sandbox is left created-but-stopped
with the registry login and the postgres image cached.

## Route B — Docker Hub (zetaris/Freemium GitHub route)

- Freemium repo cloned in the sandbox (commit in freemium-git-commit.txt);
  compose defines zetaris-db/server/api/gui + optional AI services
  (compose copy: docker-compose.freemium.yml). Documented flow:
  `docker compose pull`, `docker compose up`, add user via
  `docker compose exec zetaris-server /home/zetaris/lightning/bin/dev-account.sh`.
- `docker compose pull zetaris-db zetaris-server zetaris-api zetaris-gui`:
  postgres:15.1 pulled OK (544 MB, cached in the sandbox). All three
  Zetaris images failed: "pull access denied … may require 'docker login'".
- Docker Hub API (anonymous): `zetaris/lightning-server|lightning-api|lightning-gui`
  → "object not found" (private). The org's 5 public repos are
  lightning-catalog-nvidia, spark-operator, postgresql, postgres,
  airflow-redis — none is the Lightning stack.
- Individual pulls of zetaris/lightning-{api,gui} and server tags
  {v2.4.1.0-latest, v2.4.1.0, latest} → all denied. A Docker Hub login
  with Zetaris-granted access would be required; none is available.
- No Zetaris-run ACR found under 7 candidate hostnames (all unreachable).

## What would unblock

Either (a) the exact image references (repository + tag) for
zetarishackathon.azurecr.io from the event's participant materials —
the vaulted credential may be scoped to names only visible there — or
(b) a scope-map fix / reissued ACR credential from the event team, or
(c) Docker Hub credentials with pull access to the private zetaris/*
repos. Once any image source works, stand-up is the documented compose
flow in this same sandbox (large shape, dockerd 29.9.2, Compose v5.6.1,
postgres already cached), then source registration + the federated
query per sponsors/sources/README.md.
