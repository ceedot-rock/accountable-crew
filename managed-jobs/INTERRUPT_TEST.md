# Interrupt test — qpilot-001 (the decisive test, made executable)

Question: can Slid Phi lose an agent session halfway through authorized
work and still know what happened, what remains permitted, how to
recover, and when to stop spending — without manual reconstruction?

## Setup (preconditions)

1. qpilot-001 is `RUNNING` under the supervisor: claimed by the pilot
   executor, lease live, heartbeats arriving, checkpoint recorded.
2. The box is live with the pilot payload laid out (bundle + kit +
   bootstrap), canary attempted or running.
3. Budget consumed is reconciled from the provider before the interrupt.

## The interrupt (deliberate, one method — pick one at run time)

- A: the executor stops sending heartbeats (simulated worker death).
- B: the supervisor operator kills the worker session.
- C: the box is stopped out-of-band.
No other state is touched. The clock then runs past the 45-min lease.

## What must happen (supervisor behavior, no human digging)

1. Lease expiry is detected by the supervisor's own check; the job goes
   `ABANDONED`, authority is revoked for further execution, and the
   resource is flagged for teardown review.
2. Reconcile runs from external reads only: does the pod exist, what was
   actually spent, what checkpoint survives. No action is re-issued
   blindly; completed actions from the idempotency log are skipped.
3. The supervisor (or Corey, as escalation owner) decides resume or
   cancel, with the reason recorded:
   - Resume: only after reconcile, back to `CLAIMED` (never straight to
     `RUNNING`), then heartbeats resume.
   - Cancel: authority revoked, teardown requested for the resource,
     budget reconciled to a final figure.
4. Teardown proof is recorded (pod stopped + final cost) before the job
   leaves the system.
5. One final record is emitted linking authority, execution, cost, and
   outcome, with its SHA-256.

## Pass criteria (all five, or the test FAILS)

- [ ] Last checkpoint + last heartbeat time readable from the job record.
- [ ] Remaining authority (cap left, lease state) readable from the record.
- [ ] Resume-or-cancel decision + reason recorded in the history.
- [ ] Teardown proof + final cost recorded.
- [ ] Final record complete — with NO manual reconstruction from chat
      logs, DM threads, or memory by the operator. If any item required
      digging, the test fails even if the pilot itself later succeeds.

## What this test does NOT prove (honest limits)

- Cloud-side enforcement: the supervisor cannot force Runpod to stop a
  pod. Teardown here is requested + attested + reconciled against the
  provider's own reads. A cloud-enforced kill switch is later work.
- Heartbeat transport over the Rider DM rail (v1 heartbeats are
  supervisor API calls reconciled from executor reports). A DM-transport
  test is a separate v2 item, and it must be designed for a lossy
  channel.
- CuNi anchoring of the final record (v1 emits the hash; anchoring is v2).
