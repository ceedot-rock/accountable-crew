#!/usr/bin/env python3
"""agent_loop.py — one agent seat for the Accountable Agent Crew.

Verified integration points (live-probed 2026-10-22 against
https://agentrider.fly.dev, 66 MCP tools):

- register{name, type:"agent", capabilities} -> {agent_id, api_key,
  credits} — new seats start with 20 AGC. The api_key (ar_...) is a
  credential: stored 0600 under ../.keys/, never logged, never
  receipted.
- issue_rider{api_key} -> {rider: <ES256 JWT>, expires_in: 900,
  mode: "live"} — the JWT is passed as `rider_token` on gated tools.
- verify_rider{rider_token} -> {valid, rider:{agent_id, level, ...}}.
- Hire rail: post_task{rider_token,title,description,category,reward}
  (reward 5–500 AGC, escrowed immediately) -> claim_task (costs the
  claimer 1 AGC) -> submit_task{result} -> approve_task (releases
  escrow to the worker) / reject_task{reason} (refunds the poster).
- check_balance{rider_token} -> {credits, tasksCompleted}.

Model access is NOT here: plan() delegates to providers.py, the single
provider seam (nemotron-direct / openrouter configs; neither key
exists on this VM yet, so a model plan raises ProviderNotConfigured —
by design, never silently). Spending never happens here either: paid
calls go through ../mandate-gate (gate first, always).
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / "workspace" / "agent-rider"))
from mcp_client import MCPClient  # noqa: E402  (verified live: 66 tools)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import providers  # noqa: E402

KEYS_DIR = Path(__file__).resolve().parent.parent / ".keys"


class RiderError(RuntimeError):
    """A Rider tool returned ok:false or an unparseable result."""

    def __init__(self, tool: str, payload):
        self.tool = tool
        self.payload = payload
        super().__init__(f"rider tool {tool} failed: {payload!r:.300}")


def _parse_result(res) -> dict:
    """MCP tools/call result -> the tool's JSON dict."""
    if isinstance(res, dict) and "content" in res:
        text = "\n".join(p.get("text", "") for p in res["content"]
                         if isinstance(p, dict))
        try:
            return json.loads(text)
        except ValueError:
            return {"raw": text}
    if isinstance(res, dict):
        return res
    return {"raw": str(res)}


class RiderTools:
    """Thin, honest wrapper over MCPClient: returns parsed dicts,
    raises RiderError when the tool reports ok:false."""

    def __init__(self, client: MCPClient | None = None):
        self.client = client or MCPClient()
        self._initialized = False

    def call(self, name: str, arguments: dict) -> dict:
        if not self._initialized:
            self.client.initialize()
            self._initialized = True
        out = _parse_result(self.client.call_tool(name, arguments))
        if isinstance(out, dict) and out.get("ok") is False:
            raise RiderError(name, out)
        return out


def _jwt_exp(token: str) -> int:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return int(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except Exception:
        return 0


class CrewAgent:
    """A single crew seat: Rider identity + provider plan + hire rail."""

    def __init__(self, seat_name: str, capabilities: list[str] | None = None,
                 keys_dir: Path | None = None, tools: RiderTools | None = None):
        self.seat_name = seat_name
        self.capabilities = capabilities or ["general"]
        self.keys_dir = Path(keys_dir) if keys_dir else KEYS_DIR
        self.tools = tools or RiderTools()
        self.agent_id: str | None = None
        self._api_key: str | None = None
        self._token: str | None = None
        self._load_stored_identity()

    # --- identity ------------------------------------------------------
    def _key_path(self) -> Path:
        return self.keys_dir / f"{self.seat_name}.ar_key"

    def _id_path(self) -> Path:
        return self.keys_dir / f"{self.seat_name}.agent_id"

    def _load_stored_identity(self) -> None:
        if self._key_path().exists():
            self._api_key = self._key_path().read_text().strip()
        if self._id_path().exists():
            self.agent_id = self._id_path().read_text().strip()

    def register(self) -> dict:
        """Register this seat on Rider (once) and vault its API key.

        Returns {agent_id, credits} — never the key. If a vaulted key
        exists but the agent_id file is missing, the id is recovered
        from issue_rider's response — NEVER by re-registering (a second
        register() silently mints a second seat and orphans the first
        seat's key; learned on the first driver run, 2026-10-22).
        """
        if self._api_key and self.agent_id:
            return {"agent_id": self.agent_id, "already_registered": True}
        if self._api_key:
            self.token()  # issue_rider response carries the agent_id
            return {"agent_id": self.agent_id, "already_registered": True,
                    "recovered_via": "issue_rider"}
        out = self.tools.call("register", {
            "name": self.seat_name, "type": "agent",
            "capabilities": self.capabilities,
        })
        self.agent_id = out["agent_id"]
        self._api_key = out["api_key"]
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._key_path(),
                     os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(self._api_key)
        self._id_path().write_text(self.agent_id)
        return {"agent_id": self.agent_id, "credits": out.get("credits")}

    def token(self) -> str:
        """A live rider JWT for this seat (re-issued when <120s left)."""
        if self._token and _jwt_exp(self._token) - time.time() > 120:
            return self._token
        if not self._api_key:
            raise RiderError("issue_rider", "seat not registered yet")
        out = self.tools.call("issue_rider", {"api_key": self._api_key})
        self._token = out["rider"]
        if out.get("agent_id") and out["agent_id"] != self.agent_id:
            self.agent_id = out["agent_id"]
            self.keys_dir.mkdir(parents=True, exist_ok=True)
            self._id_path().write_text(self.agent_id)
        return self._token

    def verify_identity(self) -> dict:
        return self.tools.call("verify_rider",
                               {"rider_token": self.token()})

    def balance(self) -> dict:
        return self.tools.call("check_balance",
                               {"rider_token": self.token()})

    # --- hire rail -------------------------------------------------------
    def post_task(self, title: str, description: str, reward_agc: int,
                  category: str = "general", input_obj: dict | None = None,
                  acceptance: str | None = None) -> dict:
        args = {"rider_token": self.token(), "title": title,
                "description": description, "category": category,
                "reward": reward_agc}
        if input_obj is not None:
            args["input"] = json.dumps(input_obj)
        if acceptance:
            args["acceptanceCriteria"] = acceptance
        return self.tools.call("post_task", args)

    def claim_task(self, task_id: str) -> dict:
        return self.tools.call("claim_task", {"rider_token": self.token(),
                                              "taskId": task_id})

    def submit_task(self, task_id: str, result: str) -> dict:
        return self.tools.call("submit_task", {"rider_token": self.token(),
                                               "taskId": task_id,
                                               "result": result})

    def approve_task(self, task_id: str) -> dict:
        return self.tools.call("approve_task", {"rider_token": self.token(),
                                                "taskId": task_id})

    def reject_task(self, task_id: str, reason: str) -> dict:
        return self.tools.call("reject_task", {"rider_token": self.token(),
                                               "taskId": task_id,
                                               "reason": reason})

    def get_task(self, task_id: str) -> dict:
        return self.tools.call("get_task", {"taskId": task_id})

    def send_dm(self, to_agent_id: str, content: str) -> dict:
        return self.tools.call("send_direct_message", {
            "rider_token": self.token(), "toAgentId": to_agent_id,
            "content": content})

    # --- model -----------------------------------------------------------
    def plan(self, job: str, context: dict | None = None,
             provider: str = "scripted") -> list[dict]:
        """Break `job` into subtasks via the provider seam.

        Default provider is "scripted" (deterministic, model-free) so
        the loop is exercisable today; pass provider="nemotron-direct"
        or "openrouter" once that key exists — plan() then raises
        ProviderNotConfigured until it does.
        """
        return providers.plan_with_provider(provider, job, context or {})

    # --- convenience orchestration ---------------------------------------
    def run(self, job: str, context: dict | None = None,
            provider: str = "scripted", reward_agc: int = 5) -> dict:
        """Lead-side convenience: plan a job and post every subtask.

        Escrow is the post itself (Rider holds the reward until
        approve/reject). Mandate gating of *paid calls* inside subtask
        execution is the driver's / worker's path via mandate-gate —
        see driver.py for the full Scenario-1 pipeline.
        """
        subtasks = self.plan(job, context, provider=provider)
        posted = []
        for st in subtasks:
            out = self.post_task(
                title=st["title"], description=job, reward_agc=reward_agc,
                input_obj={"job": job, "subtask": st},
                acceptance="Deliver the subtask result via submit_task.")
            posted.append({"subtask": st, "task": out.get("task", out)})
        return {"job": job, "provider": provider, "posted": posted}


if __name__ == "__main__":
    raise SystemExit("library — see README.md; run driver.py for the "
                     "end-to-end pipeline")
