# The Developer Codex — how to run a coding agent so the result survives

This is the operating manual for a codebase where agents do most of the typing.

It is not advice. Every law below was a real failure first — something shipped
broken, cost a day, and got written down so it could not happen silently again.
The evidence is measured, and where a number appears it was counted rather than
estimated.

Read it in order the first time. After that it is a lookup table.

---

## Who this is for

**You have never used a coding agent.** Start at
[the path](path/00-welcome.md) — the Aither World Guide, from "what is an agent?"
to a terminal that answers you, with the command to type beside every idea it
teaches. The chapters and their order are mirrored from
[awknowledge](https://github.com/Aitherium/awknowledge); `journey.yaml` is the one
source for both.

**You already use one and it keeps producing confident garbage.** Skip to
[LAW 1](laws/01-a-rule-nothing-asserts-is-a-suggestion.md). The problem is almost
never the model.

**You are building the harness itself.** The twenty-nine laws are the whole point.
Read [Silence](#ii--silence) first — those five are the ones that cost the most
per incident, because nothing tells you they happened.

---

## The path — from nothing to a working setup

<!-- path:start GENERATED from journey.yaml by check_awskills_docs.py --write. Edit journey.yaml, not this table. -->
| | |
|---|---|
| [00 · Welcome to Aither World](path/00-welcome.md) | What Aitherium, AitherOS and the aw* bricks are - in plain words, before you install anything. |
| [01 · Install awdk](path/01-install-awdk.md) | One command puts the whole kit on your machine. Then you check it worked. |
| [02 · Your first local brain](path/02-first-brain.md) | Run an open model on your own computer, offline. Learn what "8B" and "1-bit" actually mean. |
| [03 · Talk to it](path/03-talk-to-it.md) | Ask your brain one question, then open a chat. Optionally connect to the cloud for the bigger brains. |
| [04 · Build your first agent](path/04-build-an-agent.md) | An agent is a brain plus tools plus a job. You will scaffold one in three files and watch it use a tool. |
| [05 · Agent packs](path/05-agent-packs.md) | Someone already built the agent you want. Find it, install it, run it - and know what is still coming. |
| [06 · Your own hardware](path/06-your-own-hardware.md) | CPU or GPU, laptop or rack - how the open model stack picks a model for what you have, and how a brain gets registered. |
| [07 · Deploy on awnix](path/07-deploy-on-awnix.md) | An immutable Linux built for machines where software writes software. Your agent becomes three lines in a Dockerfile. |
| [08 · Many agents, one repo](path/08-many-agents.md) | Two agents editing the same code without sweeping each other's work - leases, a call graph, messaging, memory. |
| [09 · The omnibox](path/09-omnibox.md) | Your terminal answers you. Type a question where a command would go. |
| [10 · Build a pack](path/10-build-a-pack.md) | Write a tool pack, check it without running it, load it the way an agent will, and build bytes anyone can verify. |
| [11 · Set up Claude Code the Aither way](path/11-claude-code.md) | Put every aw* brick in Claude Code as tools, skills and hooks with one command, then check it stays that way. |
<!-- path:end -->

## The doctrine — how to prompt and steer

Two skills in this pack carry the operating doctrine. They are mined from
27,939 prompts across 3,183 sessions over 210 days, re-measured on a disjoint
34-day window.

- [`code-like-david`](../skills/code-like-david.md) — the thirteen rules: prompt
  shape, live-proof gates, plan documents as files, persistent memory, when to
  orchestrate, when to compact, how to route models.
- [`ramble-driven-development`](../skills/ramble-driven-development.md) — the
  shape law. Median human prompt: 56 characters. The 5.9% over 1,000 chars carry
  78% of everything typed. There is nothing useful in between.

**The one sentence:** the fully-specified prompt still has to exist — you just
should not be the one typing it. You do not type your standards. You install them.

---

<!-- laws:start GENERATED from the awknowledge laws/*.md. Edit those files, not this list. -->
## The twenty-nine laws

### I · Enforcement
*A standard nothing checks is a preference. How a preference becomes a property of the codebase - and why a checker nobody has watched fail is not a gate.*

1. [A rule nothing asserts is a suggestion](laws/01-a-rule-nothing-asserts-is-a-suggestion.md)
2. [Make it a check, not a ticket](laws/02-make-it-a-check-not-a-ticket.md)
3. [Watch your gate fail](laws/03-watch-your-gate-fail.md)
4. [Mutate the test, not just the code](laws/04-mutate-the-test-not-just-the-code.md)

### II · Silence
*The expensive failures do not raise. They return 200, render correctly, log nothing, and leave the container healthy. A missing thing is indistinguishable from a thing nobody wanted.*

5. [Design for the silence](laws/05-design-for-the-silence.md)
6. [A check that cannot run must not pass](laws/06-a-check-that-cannot-run-must-not-pass.md)
7. [The symptom names the innocent](laws/07-the-symptom-names-the-innocent.md)
8. [A checker in the wrong place found nothing](laws/08-a-checker-in-the-wrong-place-found-nothing.md)
9. [Detection without delivery is not detection](laws/09-detection-without-delivery-is-not-detection.md)

### III · Adoption
*A gate only works while people keep it switched on. Most gates die of being right too loudly - so narrow the rule, pin the count, ratchet down.*

10. [A gate that floods gets switched off](laws/10-a-gate-that-floods-gets-switched-off.md)
11. [Open green, ratchet down](laws/11-open-green-ratchet-down.md)
12. [Measure it again](laws/12-measure-it-again.md)

### IV · Deployment
*The gap between the code you wrote and the code that is running. A build can succeed and ship nothing; a live mount makes the file current and leaves the process stale.*

13. [Written is not deployed](laws/13-written-is-not-deployed.md)
14. [You wrote it; that does not mean it ships](laws/14-you-wrote-it-that-does-not-mean-it-ships.md)
15. [Generate, never copy](laws/15-generate-never-copy.md)
16. [The defect lives in the union](laws/16-the-defect-lives-in-the-union.md)

### V · Trust
*Patterns no linter will catch, because they are semantic: the gate that fails open, the decision keyed on input the caller chose, the count that measures the wrong thing.*

17. [Fail closed, then prove the happy path](laws/17-fail-closed-then-prove-the-happy-path.md)
18. [Never trust the caller for an authorization decision](laws/18-never-trust-the-caller.md)
19. [Count the closure, not the edge](laws/19-count-the-closure-not-the-edge.md)
20. [A platform you cannot ship to is not supported](laws/20-a-platform-you-cannot-ship-to-is-not-supported.md)

### VI · Configuration
*A setting is only real if it survives a restart and reaches the process that reads it. A cap in a file nothing loads is a wish; a decision several agents make together needs a channel a human can read.*

21. [A cap that does not survive a restart is not a cap](laws/21-a-cap-that-does-not-survive-a-restart-is-not-a-cap.md)
22. [Coordinated decisions need a channel humans can read](laws/22-coordinated-decisions-need-a-channel-humans-can-read.md)

### VII · Scaling
*Where the numbers stop meaning what they used to. A mixture-of-experts model has two budgets, not one, and a plan that adds capacity without asking which one it feeds adds nothing.*

23. [A mixture-of-experts model has two budgets, not one](laws/23-a-mixture-of-experts-model-has-two-budgets-not-one.md)
24. [The always-on context is a budget](laws/24-the-always-on-context-is-a-budget.md)
25. [A setting in a scope nobody reads does not exist](laws/25-a-setting-in-a-scope-nobody-reads-does-not-exist.md)
26. [A hook on every call spends a latency budget](laws/26-a-hook-on-every-call-spends-a-latency-budget.md)
27. [One sanction file, never scattered](laws/27-one-sanction-file-never-scattered.md)
28. [A guard in one direction is half a guard](laws/28-a-guard-in-one-direction-is-half-a-guard.md)
29. [Portable is files and presets, never credentials](laws/29-portable-is-files-and-presets-never-credentials.md)
<!-- laws:end -->

---

## How the laws are meant to be used

Not as a reading list. Each law names **the check that enforces it**, because a
law you have to remember is a law you will forget at 2am with a red build.

The working loop is four steps and it is the whole method:

```
something breaks
  → you fix it
  → you ask: could a check have caught this?
  → if yes, THE CHECK IS THE WORK. Write it, watch it fail, wire it somewhere
    unattended. Do not write a ticket.
```

A codebase run this way gets harder to break over time without anyone having to
be careful. That is the entire claim, and it is the only one worth making.

---

*Part of [awskills](../README.md) — MIT licensed, free to fork and adapt.*
