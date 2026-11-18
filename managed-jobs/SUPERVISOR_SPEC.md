# Supervisor v1 — operational control plane for Accountable Crew

Not another agent, chat room, or dashboard. The thing that knows: this job
is running here, under this authority, spending against this budget,
producing this evidence — and here is what happens if it stalls.

V1 scope, deliberately small: **job record + lease + capability check +
acceptance test + teardown.** It extends Accountable Crew's existing
mandate gate (spend authorization) and receipt trail (CuNi envelopes) with
the enforcement layer those pieces do not supply. It does not replace
Rider (identity/delegation), Warrant (authority), CuNi (evidence), or psi
(continuity) — it supervises jobs that use them.

## The job record (one persistent record per job)

```
job_id, owner, executing_agent, executor
objective, acceptance_tests[]          # each: name + independent verifier
authority_reference, authority_expiry, authority_revoked
budget_reserved, budget_consumed
state, heartbeat_at, lease_expiry
checkpoint, artifact_references[]
completed_actions[]                    # action_id -> outcome (idempotency log)
next_action, blocker, escalation_owner
history[]                              # append-only transitions + reasons
resource_id, teardown_proof
```

## States (enforced, not advisory)

`SUBMITTED → CAPABILITY_CHECKED → CLAIMED → RUNNING → COMPLETED /
CANCELLED / FAILED`, with `BLOCKED` reachable from `SUBMITTED` /
`CAPABILITY_CHECKED`, and `ABANDONED` reachable from `CLAIMED` / `RUNNING`
on lease expiry. Terminal states (`COMPLETED`, `CANCELLED`, `FAILED`)
have no exits. `ABANDONED` resumes only to `CLAIMED` and only after a
reconcile — never directly back to `RUNNING`, never without knowing what
already happened. The old vocabulary maps onto this machine: "claimed" =
`CLAIMED`, "alive" = `RUNNING` with a fresh heartbeat, "making progress"
= `RUNNING` with fresh checkpoints, "blocked" = `BLOCKED` with a named
blocker and escalation owner, "abandoned" = `ABANDONED` after lease
expiry. A job is never just "a task" with one status again.

## Leases

A claim is time-bounded. Default: heartbeat every 15 min, lease 45 min
(three missed beats = expired). Heartbeats are valid only in `CLAIMED` /
`RUNNING`. On expiry the supervisor marks the job `ABANDONED`, revokes
its authority for further execution, and flags its resource for teardown
review. Expiry is detected by the supervisor checking leases — it does
not depend on the worker announcing its own death. **If a worker
disappears, its spending authorization must not silently become permission
to leave an orphaned resource running indefinitely.** That rule is
enforced here: no valid lease, no further spend, teardown required.

## Capability registry (per executor, tested, not claimed)

Each executor record holds: machine + runtime, tools installed and
authenticated, actions it can *perform* versus merely *describe*,
authority expiry, and when its capabilities were last tested. The
dispatcher routes a job only to an executor whose check passes fresh
(default freshness: 24 h) with every required tool authenticated and every
required action in its perform set. Otherwise the job goes `BLOCKED`
with the precise missing list — never to an executor that will fail
mid-job for a foreseeable reason. The Runpod exchange is the exhibit:
a documentation-capable agent must never receive an execution job.

## Resource lifecycle (the managed unit is the whole experiment)

`authorize → provision → verify environment → execute → checkpoint →
collect artifacts → stop compute → reconcile cost.` The mandate gate
already answers "is this payment permitted." The supervisor binds the
rest to the same job and authority: provisioning, ongoing use, and
teardown are recorded against the job, and cost reconciliation is part
of completion, not an afterthought. A job with a resource completes
only with teardown proof recorded (stopped/terminated + final cost).

## Recovery without duplicating side effects (reconcile before retry)

- Retrying a computation skips actions already in `completed_actions`.
- Retrying an uncertain payment or provisioning request reconciles via
  an external read first (does the pod exist? what was actually spent?),
  never by blind re-issue.
- Resuming a checkpoint requires a reconcile since abandonment.
- Cancelling revokes remaining authority and requires teardown.
- Partial completion is compensated by recording exactly what finished
  and what did not — the final record never claims more than the
  evidence carries.
**"Worker died" must not automatically mean "repeat every action."**

## Acceptance tests (verify the outcome, not just the trail)

Every job carries its acceptance tests *before dispatch*. The executing
agent's self-report is evidence, never the verdict: completion requires
every test's independent verifier to pass on the collected evidence.
Examples: quantum experiment → official integer-word verifier passes;
deployment → approved version healthy at the intended endpoint; code
change → required tests pass against the submitted commit; research
task → claims carry the required evidence and unresolved contradictions
are explicit. A job whose acceptance tests fail stays `RUNNING` with
the failed checks as its blocker — it is not marked done.

## Final record

One record linking authority, execution, cost, and outcome, with a
SHA-256 over its canonical JSON so a later CuNi anchor can bind it.
The supervisor emits it on completion, cancellation, and failure alike.

## V1 limits (stated, not hidden)

- Heartbeats are supervisor API calls reconciled from executor reports.
  Automated heartbeat transport over the Rider DM rail is v2 — and it
  must be designed for a lossy channel (timeouts, not delivery
  guarantees), because today even message receipt is unprovable.
- The supervisor cannot force a cloud to stop a pod. Teardown is a
  requested + attested action recorded against the job, and the spend
  gate is enforced at the supervisor (no lease = no further authorized
  spend). Cloud-side enforcement is a later step, not a v1 claim.
- CuNi anchoring of final records is v2; v1 emits the hash the anchor
  will bind.
- Single supervisor instance, local job files. No high availability
  claim. Job files live in `managed-jobs/jobs/`; the supervisor never
  touches `accountable-crew/.keys/` or any private key material.
