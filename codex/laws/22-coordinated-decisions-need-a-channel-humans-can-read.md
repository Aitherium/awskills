# Coordinated decisions need a channel humans can read — the audit trail law
*Part VI · Configuration*

**Fires when:** agents or automations make decisions that affect the platform,
and those decisions are routed through internal APIs or message queues.

## The law

A decision made inside an automated system is invisible to the humans who inherit
its consequences. If the decision is revoked, changed, or undone later, the
historical record lives only in the automation itself — a transcript, a log level
below normal verbosity, or a memory the person who made it never wrote down.

**If humans cannot read the decision as it is being made, the decision is not
coordinated. It is silent.**

Coordination requires a channel that:
1. **Is public to the relevant humans** — not buried in a log file or an internal
   API response.
2. **Preserves the decision** — both the action and the reasoning — in a place
   those humans can find it later.
3. **Allows humans to veto or reverse it** — or at least to have done so before
   the action finishes.
4. **Is asynchronous** — the human does not have to be online at the moment the
   decision is made.
5. **Is audit-able** — a third party (an owner, a regulator, or a future
   developer) can ask "what decided this?" and find an answer.

Without all five of these, the channel is not coordination — it is a notification
in one direction, and one direction is not enough.

## Why this matters

Automated decisions are being made faster and more frequently. A coding agent can
steer infrastructure, start expensive cloud jobs, or change a deployment — all
without a human physically typing the commands. That is the design. But the
decision to do these things **originated somewhere**, and that origin is not the
machine.

If the decision is silent, then:
- **No two humans share context.** One person sees the result of a decision; a
  second person sees only the current state and does not know what changed it.
- **Reversals are invisible.** A decision is made, something breaks, the decision
  is undone — and the next person inherits a system in an intermediate state with
  no record of how it got there.
- **Debugging is impossible.** A system behaves unexpectedly. Someone asks "what
  changed?" The answer lives inside an agent's decision-making, or in a CI log
  filtered to ERROR level, or not at all.
- **The platform becomes unmaintainable.** A new person cannot learn how the
  system works because the decisions are not visible. Configuration begins to
  diverge from documentation. "Why is this this way?" becomes unanswerable.

## The three grades of channel

**Grade A: interactive (steering while running)**
  - Decision-card surfaces: a human sees a proposed action and approves/rejects it
    before the automation runs.
  - Used for: high-impact decisions, rollouts, approval gates.

**Grade B: asynchronous with veto (documented before the action is irreversible)**
  - A human-readable channel receives the decision, reason, and result.
  - The human can veto the action before it finishes (e.g. before a deployment
    completes).
  - Used for: important but lower-impact decisions, routine actions that should
    be visible.

**Grade C: audit-able after the fact (documented so it can be understood later)**
  - A human-readable channel has a complete record of what was decided and why.
  - The decision is already taken (irreversible).
  - Used for: routine operations that must be auditable but do not need live
    approval.

Choose the grade that fits the impact. High-impact decisions should not route
through grade C channels. Routine diagnostics do not need grade A. **But silence
— no channel — is never acceptable.**

## The check

For any automated decision, ask:
1. **Is there a human-readable channel announcing it?**
2. **Can a human find the channel later without asking you?**
3. **Does the channel include the reasoning, not just the action?**
4. **Can a human reverse it, or at least understand that it happened?**

A system that fails all four of these is a black box, not a coordinated platform.
A system that fails any one of these has a silent failure mode.

## The operational form

When you wire an agent or automation to make decisions about the platform:

1. **Decide the grade.** If you would wake an owner for this decision, it is
   grade A. If a post-mortem would need to know about it, it is grade B minimum.
2. **Wire the channel first.** Before the automation runs, ensure the decision
   lands somewhere a human can read it.
3. **Make the channel durable.** A Discord DM is readable. A console log at
   INFO level that scrolls off the screen is not. A database record is
   readable. A file that gets rotated away after one day is not.
4. **Audit the channel.** Once a month, read the channel and verify it has the
   decisions you expect. Silent decisions are a sign the automation is not
   wired correctly.
