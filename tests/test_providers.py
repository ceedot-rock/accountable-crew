#!/usr/bin/env python3
"""Provider seam tests: configuration failures are loud and specific;
the scripted provider is deterministic and validates the contract."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent-loop"))
import providers  # noqa: E402

SCRIPT = [{"title": "Do a thing", "assignee_hint": "crew-researcher",
           "budget_cents": 2}]


class Scripted(unittest.TestCase):
    def test_returns_validated_script(self):
        out = providers.plan_with_provider("scripted", "job",
                                           {"script": SCRIPT})
        self.assertEqual(out, SCRIPT)

    def test_missing_script_is_a_config_error(self):
        with self.assertRaises(providers.ProviderNotConfigured):
            providers.plan_with_provider("scripted", "job", {})

    def test_bad_budget_rejected(self):
        bad = [{"title": "x", "assignee_hint": "", "budget_cents": 2.5}]
        with self.assertRaises(providers.ProviderError):
            providers.plan_with_provider("scripted", "job", {"script": bad})

    def test_empty_plan_rejected(self):
        with self.assertRaises(providers.ProviderError):
            providers.plan_with_provider("scripted", "job", {"script": []})


class ModelProviders(unittest.TestCase):
    def test_openrouter_without_key_names_the_env_var(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(providers.ProviderNotConfigured) as cm:
                providers.plan_with_provider("openrouter", "job", {})
        self.assertIn("OPENROUTER_API_KEY", str(cm.exception))

    def test_nemotron_without_key_names_the_env_var(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(providers.ProviderNotConfigured) as cm:
                providers.plan_with_provider("nemotron-direct", "job", {})
        self.assertIn("NVIDIA_API_KEY", str(cm.exception))

    def test_nemotron_with_key_but_no_model_names_model_env(self):
        with mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "nv-test"},
                             clear=True):
            with self.assertRaises(providers.ProviderNotConfigured) as cm:
                providers.plan_with_provider("nemotron-direct", "job", {})
        self.assertIn("NEMOTRON_MODEL", str(cm.exception))

    def test_unknown_provider(self):
        with self.assertRaises(providers.ProviderError):
            providers.plan_with_provider("carrier-pigeon", "job", {})

    def test_configs_present(self):
        self.assertEqual(providers.PROVIDERS["nemotron-direct"]["key_env"],
                         "NVIDIA_API_KEY")
        self.assertEqual(providers.PROVIDERS["openrouter"]["base_url"],
                         "https://openrouter.ai/api/v1")
        self.assertEqual(
            providers.PROVIDERS["nemotron-direct"]["base_url"],
            "https://integrate.api.nvidia.com/v1")


if __name__ == "__main__":
    unittest.main()
