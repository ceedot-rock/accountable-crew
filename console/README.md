# console

The crew console: the demo surface. Three views, matching the outputs in
Day-1 answer 4:

1. **Crew view** — seats, their Rider identities, who is working on what
   (task state from the Rider MCP: `get_task`, `list_tasks`).
2. **Mandate / spend view** — each seat's warrant chain (root mandate →
   attenuated hops), cap vs spent, and every gate denial with its code
   (`OVER_BUDGET`, `WARRANT_EXPIRED`, `AGENT_MISMATCH`, `WARRANT_DENIED`).
3. **Receipt timeline** — the CuNi trail from `../receipts/trail.jsonl`,
   each entry verifiable in the browser of the demo via
   `receipts.verify_trail` results; a tampered entry must show as FAILED.

## What exists / what doesn't

- Rider's own console (`~/workspace/agent-rider/console/index.html`) is a
  single static page for the social/marketplace surface — useful as a
  styling reference only; it has no crew, mandate, or receipt views.
- This console is a new build (plan D4–D5, Sun Oct 25). Static-first: it
  reads snapshots produced by the agent loop + gate + receipts rather than
  holding its own state, so what it shows is exactly what the receipts
  prove.

## Missing evidence

- Snapshot format between the loop/gate/receipts and this UI is not fixed
  yet — it gets defined when the first end-to-end run produces a real
  trail (Sun Oct 25). `index.html` is a placeholder shell until then;
  do not build views against invented JSON shapes.
