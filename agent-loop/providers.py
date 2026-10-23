#!/usr/bin/env python3
"""providers.py — the single seam for every model call in the crew.

agent_loop.plan() never talks to a model directly; it calls
plan_with_provider(). Configs:

- "nemotron-direct": NVIDIA Nemotron via NVIDIA's OpenAI-compatible
  API (https://integrate.api.nvidia.com/v1). This is the researcher
  lane's working route per the event FAQ ("your product runs on
  NVIDIA Nemotron, either connected directly or through the Meterless
  engine") — the Meterless-engine route stays a TODO until the
  participant-login details land; nothing here claims to be it.
  Key: NVIDIA_API_KEY. Model: NEMOTRON_MODEL (no default is invented;
  Nemotron model ids differ per deployment, so it must be set).
- "openrouter": OpenRouter chat completions. Key: OPENROUTER_API_KEY.
  Model: OPENROUTER_MODEL.

A missing key or model raises ProviderNotConfigured naming the exact
environment variable — never a silent fallback, never a fabricated
plan. A malformed model response raises ProviderError.

- "scripted": NOT a model. A deterministic provider that returns
  context["script"] verbatim (validated against the subtask
  contract). It exists so the full crew pipeline — hire, mandate gate,
  paid call, receipts, verify — is testable today with zero keys, and
  so demo runs are reproducible. Anything produced through it is
  labeled "scripted" in the receipt trail.
"""

from __future__ import annotations

import json
import os

import requests

PROVIDERS = {
    "nemotron-direct": {
        "kind": "openai-chat",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key_env": "NVIDIA_API_KEY",
        "model_env": "NEMOTRON_MODEL",
    },
    "openrouter": {
        "kind": "openai-chat",
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "model_env": "OPENROUTER_MODEL",
    },
    "scripted": {"kind": "scripted"},
}

_SYSTEM = (
    "You are the planner for a crew of accountable agents. Break the job "
    "into subtasks. Reply with a JSON array only — no prose, no code "
    "fences — of objects with exactly these fields: "
    '{"title": str, "assignee_hint": str, "budget_cents": int}. '
    "Budgets are in cents and must sum to less than the job budget."
)


class ProviderError(RuntimeError):
    """A configured provider failed (HTTP, parse, or contract shape)."""


class ProviderNotConfigured(ProviderError):
    """A provider was asked to run without its key/model configured."""


def validate_subtasks(raw, provider: str) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise ProviderError(f"{provider}: plan is not a non-empty list")
    out = []
    for i, st in enumerate(raw):
        if not isinstance(st, dict):
            raise ProviderError(f"{provider}: subtask {i} is not an object")
        title = st.get("title")
        budget = st.get("budget_cents")
        if not isinstance(title, str) or not title:
            raise ProviderError(f"{provider}: subtask {i} has no title")
        if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
            raise ProviderError(
                f"{provider}: subtask {i} budget_cents is not an int >= 0")
        out.append({
            "title": title,
            "assignee_hint": str(st.get("assignee_hint", "")),
            "budget_cents": budget,
        })
    return out


def _openai_chat_plan(name: str, cfg: dict, job: str, context: dict,
                      api_key: str | None, model: str | None,
                      timeout: int) -> list[dict]:
    key = api_key or os.environ.get(cfg["key_env"])
    if not key:
        raise ProviderNotConfigured(
            f"{name}: no API key — set {cfg['key_env']} (or pass "
            "api_key=); refusing to fabricate a plan")
    mdl = model or os.environ.get(cfg["model_env"])
    if not mdl:
        raise ProviderNotConfigured(
            f"{name}: no model id — set {cfg['model_env']}; no default "
            "is assumed")
    user = json.dumps({"job": job, "context": context},
                      default=str)
    r = requests.post(
        cfg["base_url"] + "/chat/completions",
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
        json={"model": mdl,
              "messages": [{"role": "system", "content": _SYSTEM},
                           {"role": "user", "content": user}]},
        timeout=timeout,
    )
    if r.status_code != 200:
        raise ProviderError(
            f"{name}: HTTP {r.status_code}: {r.text[:200]}")
    try:
        content = r.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise ProviderError(f"{name}: unexpected response shape: {e}")
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("["):]
    try:
        raw = json.loads(text)
    except ValueError as e:
        raise ProviderError(f"{name}: model did not return JSON: {e}")
    return validate_subtasks(raw, name)


def plan_with_provider(name: str, job: str, context: dict | None = None,
                       api_key: str | None = None, model: str | None = None,
                       timeout: int = 60) -> list[dict]:
    """The one function every crew plan goes through.

    Returns [{"title": str, "assignee_hint": str, "budget_cents": int}].
    """
    context = context or {}
    cfg = PROVIDERS.get(name)
    if cfg is None:
        raise ProviderError(
            f"unknown provider {name!r}; known: {sorted(PROVIDERS)}")
    if cfg["kind"] == "scripted":
        script = context.get("script")
        if script is None:
            raise ProviderNotConfigured(
                "scripted: context['script'] is required (this provider "
                "is deterministic and model-free by design)")
        return validate_subtasks(script, name)
    return _openai_chat_plan(name, cfg, job, context, api_key, model, timeout)


if __name__ == "__main__":
    raise SystemExit("library — see README.md")
