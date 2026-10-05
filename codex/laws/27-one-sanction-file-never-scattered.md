# One sanction file, never scattered — the owner's grants live in one place
*Part V · Trust*

**Fires when:** you add an allow rule, an auto-approve, a trusted path or any standing
grant an owner has given an agent; when you cannot answer "what is this agent allowed to do
without asking?" by reading one file.

## The law

Every standing grant widens what an agent may do unobserved. If those grants are spread
across several files, layers and tools, no one can read the agent's real authority, review
a change to it, or revoke it in one edit — and a grant added in the wrong layer may be
silently dead (law 25) while the owner believes it is live.

Keep the owner's sanctions in **one file, in one layer the harness honours**, owned by the
owner. Everything else — project files, synced presets, generated configs — may reference
it but never add to it.

## The check

- A checker lists every place a grant-shaped key appears and fails when one appears
  outside the sanction file.
- The sanction file is never written by an automated sync or an agent's own edit; a change
  to it is an owner action with a visible diff.
- Revocation is one edit. If removing a grant needs a search, the grants are scattered.
