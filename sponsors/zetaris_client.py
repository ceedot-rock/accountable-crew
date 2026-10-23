"""Zetaris federated-query client — STUB over the documented REST flow only.

Documented flow (official knowledge base, kbase.zetaris.com, "Accessing
Zetaris through Rest API", read 2026-10-22):

  1. Login            -> idToken (bearer) + refreshToken
  2. OpenSqlQuery     -> body {"select": <SQL>, "pageLimit": 1..100};
                         response carries result rows + a queryToken
  3. PageSqlQuery     -> paginate with the queryToken
  4. CloseSqlQuery    -> release the cached query (HTTP 200 = closed)
  Requests carry a requestId UUID header. The base URL is the user's own
  Zetaris instance API URI, not a global endpoint.

NOT implemented, deliberately:
  - Exact endpoint paths are NOT in the knowledge-base page (it documents
    a Postman collection's folders/request names). Paths below are TODO
    placeholders to fill from the official Postman collection once an
    account/instance exists. Do not guess them.
  - No instance is running yet (see sponsors/README.md).

Stand-up state, verified 2026-10-22 (evidence: zetaris-evidence/):
  - Host: Docker Cloud sandbox "zetaris-crew", shape large
    (8 vCPU / 16 GiB), Docker Engine 29.9.2, Compose v5.6.1; the
    Freemium repo is cloned inside it and the sandbox is left
    created-but-stopped for reuse.
  - Event image registry: zetarishackathon.azurecr.io (credentials
    vaulted on the build VM at ~/.config/crew-secrets/zetaris_acr.env;
    never put them in code or logs). `docker login` against it succeeds
    from the sandbox; its WWW-Authenticate challenge is realm
    https://zetarishackathon.azurecr.io/oauth2/token, service
    zetarishackathon.azurecr.io. However, the credential's token grants
    an EMPTY access list for every repository/action probed and the
    catalog is denied, so no image reference is pullable/discoverable
    yet; the Docker Hub zetaris/lightning-* images are likewise
    private. Deployment is blocked on image acquisition — no Zetaris
    query has run through this client or any other route.
"""

from __future__ import annotations

import uuid

import requests

# TODO(evidence): replace with the real paths from the official Postman
# collection once a Zetaris instance/account exists. These are NOT
# verified endpoint paths.
_PATHS = {
    "login": "TODO-login-path",
    "open_query": "TODO-open-sql-query-path",
    "page_query": "TODO-page-sql-query-path",
    "close_query": "TODO-close-sql-query-path",
}


class ZetarisClient:
    """Minimal client for one-shot federated queries (research subtask)."""

    def __init__(self, base_url: str, email: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._email = email
        self._password = password
        self._id_token: str | None = None
        self._refresh_token: str | None = None

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._id_token}",
            "requestId": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

    def login(self) -> None:
        """Authenticate; stores idToken/refreshToken from the response."""
        raise NotImplementedError(
            "Wire once the login path + body shape are confirmed from the "
            "official Postman collection (see sponsors/README.md)."
        )

    def query(self, select_sql: str, page_limit: int = 100) -> list[dict]:
        """Run one federated SQL query and return all result rows.

        Opens the query with the documented body shape, paginates with
        the returned queryToken until exhausted, then closes the query.
        The caller (researcher agent) is responsible for receipting the
        query text + a hash of the returned rows.
        """
        raise NotImplementedError(
            "Wire once endpoint paths are confirmed (see sponsors/README.md)."
        )
