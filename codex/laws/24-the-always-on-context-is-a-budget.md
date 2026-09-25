# The always-on context is a budget — split the shared file from the harness file
*Part VI · Configuration*

**Fires when:** you add a paragraph to `CLAUDE.md`, `AGENTS.md`, or any rule file a
coding agent loads on every turn; when a subagent dies on "prompt is too long" before
its first tool call; when two harnesses (Claude Code and opencode, codex, gemini) read
different instruction files for the same repository.

## The law

Every instruction file an agent loads unconditionally is paid on **every turn of every
session**, before the agent has read a single line of your code, and compaction cannot
reclaim it. That makes it a budget, not a document. Pin the budget with a check that
fails, ratchet it down only, and treat a rule that grew as a rule to scope or split — never
as a reason to raise the pin.

Two shapes follow from that:

1. **One shared file, one harness layer.** The facts every agent needs (what the system
   is, the standing instructions, which tool to reach for first) live in a
   harness-neutral `AGENTS.md`. The harness-specific file (`CLAUDE.md`) *imports* it and
   adds only what that harness needs: how its rules load, its MCP wiring, its hooks. A
   second copy drifts; this repository measured the drift twice and lost a curated file
   to a "run the generator" fix before it stopped copying.
2. **Scope, then split by hand.** A rule that loads only when a matching path is touched
   costs nothing the rest of the time — but only the frontmatter key the harness honours
   does that (`paths:` for Claude Code; `globs:`/`alwaysApply:` do nothing and read as
   scoped). When a scoped rule is still too long, move its dated evidence to a reference
   file with a one-line pointer, and move it **by hand, section by section**: a
   heuristic splitter that infers "operative" from markup deleted a whole gate here
   while correctly trimming the line above it.

## The numbers that proved this

Measured 2026-09-21 in the monorepo, with the checker that pins it
(`check_context_floor.py`, CF001 always-applied, CF002 worst case):

| what | before | after |
|---|---|---|
| always-applied context (root file + every unscoped rule) | 8,459 tokens, over the 8,000 pin | 5,490 tokens |
| the root file alone | 10,830 chars, hand-owned, one copy | 4,326 chars importing a 6,552-char shared file |
| worst case a subagent carries before its first turn | 124,798 tokens against an 87,000 pin | falling, gate doc by gate doc |

The worst-case pin is not theoretical: on 2026-09-02 six subagents matching many path
globs consumed 1.19 M tokens and produced zero output, each dying on the prompt limit
before its first turn.

A checker that counts the root file but not what it imports would have reported the
split as an 8 KB win it never was — so the check follows the import line and its
self-test proves an imported file is counted.

## The check

- One checker owns both ceilings and exits 1 over either, 2 when it cannot read the
  files, never 0 on silence. Its self-test proves both ceilings fire in both directions.
- The floor ratchets down only. A commit that raises the pin needs a reason in the
  commit; a commit that adds an always-on paragraph pays for it by scoping or splitting
  another.
- A rule's narrative lives next to it in a reference file, never in the rule. A pointer
  line is enough; the evidence is one hop away when the rule is disputed.
