#!/usr/bin/env python3
"""Agent loop tests with a fake RiderTools (no network): identity
storage, token caching, plan delegation, hire-rail argument shaping."""
import base64
import json
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent-loop"))
sys.path.insert(0, str(Path.home() / "workspace" / "agent-rider"))
import agent_loop  # noqa: E402


def fake_jwt(agent_id: str, exp: int) -> str:
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'ES256'})}.{b64({'agent_id': agent_id, 'exp': exp})}.sig"


class FakeTools:
    def __init__(self):
        self.calls = []
        self.issued = 0

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "register":
            return {"ok": True, "agent_id": "agent-fake-1",
                    "api_key": "ar_fakekey", "credits": 20}
        if name == "issue_rider":
            self.issued += 1
            return {"ok": True, "rider": fake_jwt("agent-fake-1",
                                                  int(time.time()) + 900),
                    "expires_in": 900, "mode": "live",
                    "agent_id": "agent-fake-1"}
        if name == "verify_rider":
            return {"ok": True, "valid": True}
        if name == "check_balance":
            return {"ok": True, "credits": 20, "tasksCompleted": 0}
        if name == "post_task":
            return {"ok": True, "task": {"id": "tsk_fake"}}
        raise AssertionError(f"unexpected tool {name}")


class CrewAgentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.keys = Path(self.tmp.name)
        self.tools = FakeTools()
        self.agent = agent_loop.CrewAgent("seat-x", keys_dir=self.keys,
                                          tools=self.tools)

    def tearDown(self):
        self.tmp.cleanup()

    def test_register_stores_key_0600_and_hides_it(self):
        out = self.agent.register()
        self.assertEqual(out["agent_id"], "agent-fake-1")
        self.assertNotIn("api_key", out)
        key_file = self.keys / "seat-x.ar_key"
        self.assertTrue(key_file.exists())
        self.assertEqual(stat.S_IMODE(os.stat(key_file).st_mode), 0o600)
        self.assertEqual(self.agent.agent_id, "agent-fake-1")

    def test_register_is_idempotent_from_disk(self):
        self.agent.register()
        again = agent_loop.CrewAgent("seat-x", keys_dir=self.keys,
                                     tools=self.tools)
        out = again.register()
        self.assertTrue(out["already_registered"])
        registers = [c for c in self.tools.calls if c[0] == "register"]
        self.assertEqual(len(registers), 1)

    def test_key_without_id_file_recovers_via_issue_rider(self):
        # Only the vaulted key survived (the 2026-10-22 probe state):
        # register() must recover the id, never re-register.
        (self.keys / "seat-x.ar_key").write_text("ar_fakekey")
        agent = agent_loop.CrewAgent("seat-x", keys_dir=self.keys,
                                     tools=self.tools)
        out = agent.register()
        self.assertEqual(out["agent_id"], "agent-fake-1")
        self.assertEqual(out.get("recovered_via"), "issue_rider")
        self.assertEqual([c for c in self.tools.calls
                          if c[0] == "register"], [])
        self.assertEqual((self.keys / "seat-x.agent_id").read_text(),
                         "agent-fake-1")

    def test_token_is_cached(self):
        self.agent.register()
        t1 = self.agent.token()
        t2 = self.agent.token()
        self.assertEqual(t1, t2)
        self.assertEqual(self.tools.issued, 1)

    def test_plan_delegates_to_scripted_provider(self):
        script = [{"title": "t", "assignee_hint": "h", "budget_cents": 1}]
        out = self.agent.plan("job", {"script": script})
        self.assertEqual(out, script)

    def test_plan_model_provider_without_key_is_loud(self):
        import providers
        from unittest import mock
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(providers.ProviderNotConfigured):
                self.agent.plan("job", {}, provider="openrouter")

    def test_post_task_shapes_arguments(self):
        self.agent.register()
        out = self.agent.post_task("Title", "Desc", 5,
                                   input_obj={"a": 1}, acceptance="ok")
        self.assertEqual(out["task"]["id"], "tsk_fake")
        name, args = self.tools.calls[-1]
        self.assertEqual(name, "post_task")
        self.assertEqual(args["reward"], 5)
        self.assertEqual(json.loads(args["input"]), {"a": 1})
        self.assertEqual(args["acceptanceCriteria"], "ok")
        self.assertIn("rider_token", args)


if __name__ == "__main__":
    unittest.main()
