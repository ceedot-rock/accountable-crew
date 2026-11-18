#!/usr/bin/env python3
"""Supervisor v1: job record + lease + capability check + acceptance test
+ teardown for Accountable Crew. Standard library only. No network, no
private keys, no cloud calls — the supervisor records and enforces; the
executor performs. See SUPERVISOR_SPEC.md for the design.
"""
import hashlib
import json
import time

DEFAULT_LEASE_SECONDS = 2700          # 45 min: three missed 15-min beats
DEFAULT_CAPABILITY_TTL = 86400        # 24 h freshness for capability checks

SUBMITTED = "SUBMITTED"
CAPABILITY_CHECKED = "CAPABILITY_CHECKED"
BLOCKED = "BLOCKED"
CLAIMED = "CLAIMED"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
CANCELLED = "CANCELLED"
FAILED = "FAILED"
ABANDONED = "ABANDONED"
TERMINAL = frozenset({COMPLETED, CANCELLED, FAILED})

ALLOWED = {
    SUBMITTED: {CAPABILITY_CHECKED, BLOCKED, CANCELLED},
    CAPABILITY_CHECKED: {CLAIMED, BLOCKED, CANCELLED},
    BLOCKED: {CAPABILITY_CHECKED, CANCELLED},
    CLAIMED: {RUNNING, CANCELLED, ABANDONED},
    RUNNING: {COMPLETED, CANCELLED, FAILED, ABANDONED},
    ABANDONED: {CLAIMED, CANCELLED},
    COMPLETED: set(),
    CANCELLED: set(),
    FAILED: set(),
}


class SupervisorError(Exception):
    pass


class IllegalTransition(SupervisorError):
    pass


class BudgetRefused(SupervisorError):
    pass


class CapabilityBlocked(SupervisorError):
    pass


class ResumeRequiresReconcile(SupervisorError):
    pass


def new_job(job_id, owner, objective, acceptance_tests, authority_reference,
            budget_reserved, executing_agent="", executor="",
            authority_expiry=None, escalation_owner=""):
    """acceptance_tests: list of {"name": str} — verifiers are supplied
    independently at complete() time, never by the executor."""
    return {
        "job_id": job_id,
        "owner": owner,
        "executing_agent": executing_agent,
        "executor": executor,
        "objective": objective,
        "acceptance_tests": list(acceptance_tests),
        "authority_reference": authority_reference,
        "authority_expiry": authority_expiry,
        "authority_revoked": False,
        "budget_reserved": float(budget_reserved),
        "budget_consumed": 0.0,
        "state": SUBMITTED,
        "heartbeat_at": None,
        "lease_expiry": None,
        "checkpoint": None,
        "artifact_references": [],
        "completed_actions": {},
        "next_action": "capability check",
        "blocker": None,
        "escalation_owner": escalation_owner,
        "resource_id": None,
        "teardown_proof": None,
        "reconciled_since_abandonment": False,
        "history": [],
    }


class CapabilityRegistry:
    """Per-executor capability records. Tools must be authenticated, not
    merely installed; actions must be in the perform set, not describe."""

    def __init__(self, now_fn=None, ttl=DEFAULT_CAPABILITY_TTL):
        self._now = now_fn or time.time
        self._ttl = ttl
        self._executors = {}

    def register(self, executor_id, machine, runtime, tools, can_perform,
                 can_describe, authority_expiry=None, last_tested_at=None):
        """tools: {name: authenticated_bool}. can_perform/can_describe:
        lists of action names."""
        self._executors[executor_id] = {
            "machine": machine,
            "runtime": runtime,
            "tools": dict(tools),
            "can_perform": set(can_perform),
            "can_describe": set(can_describe),
            "authority_expiry": authority_expiry,
            "last_tested_at": (self._now() if last_tested_at is None
                               else last_tested_at),
        }

    def check(self, executor_id, required_tools, required_actions):
        """Returns (ok, missing_list). Never raises for a mismatch — a
        mismatch is a BLOCKED reason, not an exception."""
        now = self._now()
        caps = self._executors.get(executor_id)
        if caps is None:
            return False, ["executor %s not registered" % executor_id]
        missing = []
        if now - caps["last_tested_at"] > self._ttl:
            missing.append("capability check stale (last tested %ss ago)"
                           % int(now - caps["last_tested_at"]))
        if caps["authority_expiry"] is not None and now > caps["authority_expiry"]:
            missing.append("executor authority expired")
        for tool in required_tools:
            if not caps["tools"].get(tool):
                missing.append("tool not authenticated: %s" % tool)
        for action in required_actions:
            if action not in caps["can_perform"]:
                if action in caps["can_describe"]:
                    missing.append("action can only be described, not "
                                   "performed: %s" % action)
                else:
                    missing.append("action not in perform set: %s" % action)
        return (not missing), missing


class Supervisor:
    def __init__(self, registry=None, now_fn=None,
                 lease_seconds=DEFAULT_LEASE_SECONDS):
        self._now = now_fn or time.time
        self.registry = registry or CapabilityRegistry(now_fn=self._now)
        self.lease_seconds = lease_seconds

    # -- state machine -------------------------------------------------
    def _transition(self, job, new_state, reason):
        allowed = ALLOWED[job["state"]]
        if new_state not in allowed:
            raise IllegalTransition(
                "%s: %s -> %s not allowed"
                % (job["job_id"], job["state"], new_state))
        job["history"].append({
            "ts": self._now(), "from": job["state"], "to": new_state,
            "reason": reason,
        })
        job["state"] = new_state

    # -- dispatch ------------------------------------------------------
    def check_capabilities(self, job, executor_id, required_tools,
                           required_actions):
        """Routes or blocks. Returns (ok, missing)."""
        if job["state"] not in (SUBMITTED, BLOCKED):
            raise IllegalTransition(
                "capability check only from SUBMITTED/BLOCKED, not %s"
                % job["state"])
        ok, missing = self.registry.check(executor_id, required_tools,
                                          required_actions)
        if ok:
            job["executor"] = executor_id
            job["blocker"] = None
            job["next_action"] = "claim"
            self._transition(job, CAPABILITY_CHECKED,
                             "capability check passed for %s" % executor_id)
        else:
            job["blocker"] = "; ".join(missing)
            job["next_action"] = "resolve blocker or choose another executor"
            self._transition(job, BLOCKED,
                             "capability check failed: %s" % job["blocker"])
        return ok, missing

    def claim(self, job, executor_id):
        if job["state"] != CAPABILITY_CHECKED and not (
                job["state"] == ABANDONED
                and job["reconciled_since_abandonment"]):
            if job["state"] == ABANDONED:
                raise ResumeRequiresReconcile(
                    "%s: resume requires reconcile since abandonment"
                    % job["job_id"])
            raise IllegalTransition(
                "claim only from CAPABILITY_CHECKED, not %s" % job["state"])
        if job["state"] == ABANDONED:
            # Resume path: the reconcile already established what happened.
            job["reconciled_since_abandonment"] = False
        job["executor"] = executor_id
        now = self._now()
        job["heartbeat_at"] = now
        job["lease_expiry"] = now + self.lease_seconds
        job["authority_revoked"] = False
        job["next_action"] = "start execution"
        self._transition(job, CLAIMED, "claimed by %s" % executor_id)

    # -- liveness ------------------------------------------------------
    def heartbeat(self, job):
        if job["state"] not in (CLAIMED, RUNNING):
            raise IllegalTransition(
                "heartbeat only in CLAIMED/RUNNING, not %s" % job["state"])
        now = self._now()
        job["heartbeat_at"] = now
        job["lease_expiry"] = now + self.lease_seconds
        if job["state"] == CLAIMED:
            job["next_action"] = "execution"
            self._transition(job, RUNNING, "first heartbeat: execution live")

    def expire_lease(self, job):
        """Returns True if the lease expired and the job was abandoned."""
        if (job["state"] in (CLAIMED, RUNNING)
                and job["lease_expiry"] is not None
                and self._now() > job["lease_expiry"]):
            job["authority_revoked"] = True
            job["blocker"] = "lease expired: no heartbeat"
            job["next_action"] = ("reconcile, then resume or cancel; "
                                  "resource flagged for teardown review")
            self._transition(job, ABANDONED, "lease expired")
            return True
        return False

    def checkpoint(self, job, checkpoint_data):
        if job["state"] != RUNNING:
            raise IllegalTransition(
                "checkpoint only in RUNNING, not %s" % job["state"])
        job["checkpoint"] = checkpoint_data
        job["heartbeat_at"] = self._now()
        job["lease_expiry"] = self._now() + self.lease_seconds

    # -- money + actions (idempotent) ----------------------------------
    def record_spend(self, job, action_id, amount, note=""):
        if job["state"] in TERMINAL or job["state"] == ABANDONED \
                or job["authority_revoked"]:
            raise BudgetRefused(
                "%s: no spend in state %s" % (job["job_id"], job["state"]))
        if action_id in job["completed_actions"]:
            return False  # already recorded: never double-count
        if job["budget_consumed"] + amount > job["budget_reserved"]:
            raise BudgetRefused(
                "%s: %.2f + %.2f exceeds reserved %.2f"
                % (job["job_id"], job["budget_consumed"], amount,
                   job["budget_reserved"]))
        job["budget_consumed"] += amount
        job["completed_actions"][action_id] = {
            "kind": "spend", "amount": amount, "note": note,
            "ts": self._now(),
        }
        return True

    def record_action(self, job, action_id, outcome):
        """Idempotent completion log: a retry skips what is already here."""
        if action_id in job["completed_actions"]:
            return False
        job["completed_actions"][action_id] = {
            "kind": "action", "outcome": outcome, "ts": self._now(),
        }
        return True

    def reconcile(self, job, observed_actions, observed_spend_total=None):
        """Apply externally observed facts (pod exists? what was spent?).
        Idempotent by action_id. Required before resume from ABANDONED."""
        for action_id, outcome in observed_actions.items():
            self.record_action(job, action_id, outcome)
        if observed_spend_total is not None:
            # Observed spend is ground truth from the provider, not a
            # second charge: set, never add, and never below recorded.
            job["budget_consumed"] = max(job["budget_consumed"],
                                         float(observed_spend_total))
        job["reconciled_since_abandonment"] = True
        job["blocker"] = None
        job["next_action"] = "resume or cancel"

    # -- completion, cancellation, failure ------------------------------
    def complete(self, job, evidence, verifiers):
        """verifiers: {test_name: callable(evidence) -> bool}, supplied
        independently of the executor. Returns (ok, failed_names). The
        executor's self-report is evidence, never the verdict."""
        if job["state"] != RUNNING:
            raise IllegalTransition(
                "complete only from RUNNING, not %s" % job["state"])
        failed = [t["name"] for t in job["acceptance_tests"]
                  if not verifiers.get(t["name"], lambda e: False)(evidence)]
        if job["resource_id"] and not job["teardown_proof"]:
            failed.append("teardown_proof_missing")
        if failed:
            job["blocker"] = "acceptance failed: %s" % ", ".join(failed)
            job["next_action"] = "fix evidence or cancel"
            return False, failed
        job["blocker"] = None
        job["next_action"] = "final record emitted"
        self._transition(job, COMPLETED, "all acceptance tests passed")
        return True, []

    def cancel(self, job, reason):
        if job["state"] in TERMINAL:
            raise IllegalTransition("cannot cancel terminal %s" % job["state"])
        job["authority_revoked"] = True
        if job["resource_id"]:
            job["next_action"] = "teardown resource %s" % job["resource_id"]
        self._transition(job, CANCELLED, reason)

    def fail(self, job, reason):
        if job["state"] != RUNNING:
            raise IllegalTransition(
                "fail only from RUNNING, not %s" % job["state"])
        job["authority_revoked"] = True
        self._transition(job, FAILED, reason)

    # -- final record ----------------------------------------------------
    def final_record(self, job):
        record = {k: job[k] for k in sorted(job)}
        digest = hashlib.sha256(
            json.dumps(record, sort_keys=True,
                       separators=(",", ":")).encode()).hexdigest()
        return {"record": record, "sha256": digest}
