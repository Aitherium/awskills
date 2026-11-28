# Use the lane — a missing capability is priority one, and hand-rolling is never the answer
*Part III · Adoption*

**Fires when:** an agent is about to type a command or write a file to do a job, and a
platform lane may already do it — or a lane exists but is broken, which tempts a quick
beside-the-platform script.

## The law

Almost every job already has a lane: an MCP tool (`mcp__aitheros__*`), a CLI (`awrun`,
`awgit`, `awsettings`, `awrelay`, `awm`, `awkno`), a media-forge op, or a declared
workflow. The right move is to **find and extend**, never to invent a parallel script. If
the capability genuinely does not exist, or exists and is broken, then **building or
repairing it in its own repository is the job — priority 1, before the task that needed
it.** A hand-rolled script beside the platform is a second implementation that nobody
maintains, that bypasses the lease, the audit trail and the deploy lane, and that the next
agent will not find.

Measured, repeatedly, against five dates of the same instruction (2026-11-11, 11-13,
11-16 ×2, 11-18). On 2026-11-18 alone, sessions still: detached a render with
`Start-Process bash.exe -WindowStyle Hidden`; hand-wrote `render.sh`, `assemble.sh`,
`kokoro-unit-fix.sh` and `kokoro-check.sh` under `Temp` and `E:` with no repo; ran a raw
`wsl nsenter -t 1 -m sh /mnt/c/.../Temp/kokoro-unit-fix.sh --apply` against live systemd
units; generated pack data with a Python heredoc and built a client film with hand-written
ffmpeg concat/mux instead of the `film_assemble`/`mux_audio` ops; ran `gh release create`
with hand-written notes outside a delivery lane; orchestrated with a `run_in_background`
`until … sleep … done` loop driving `assemble.sh`; and removed a lock dir by hand and
launched a desktop app with `Start-Process wslg.exe`. Memory and prose did not stop it, so
the rule now ships with a guard and a check.

The rule has three parts an agent MUST be able to answer before it acts:

1. **Which lane already does this?** (capability list, op catalogue, `awkno -k <verb>`,
   the package registry). If one exists, use it and say which.
2. **If none exists or it is broken** — file it on Atlas (`tasks_create priority=1`) and
   fix it in its own repo first; then run the job.
3. **Never** start a bare or detached process, never author a loose script outside a git
   work tree, and never edit a live service's units from a host temp file.

Read-only probes, the platform CLIs, the repo's own gates (`pr_local_verify.py`,
`pr_local_review.py`, `awgit pr merge`, the deploy-tree sync), and git/gh PR flow inside
a worktree are the lane — they are allowed without a bypass. A deliberate exception is
visible: `AW_PLATFORM_FIRST_OK=1 <cmd>` runs the command and records one row (rule id,
session, sha256 and first 80 chars) to the bypass ledger; `AW_PLATFORM_FIRST_OFF=1`
disables the guard and says so on stderr.

## The check

- `check_platform_first.py` asserts the PreToolUse guard is wired (in the repo settings
  and in the portable hook set), has a self-test, **denies every command from the seven
  2026-11-18 shapes**, and **allows** the read-only / platform-CLI / gate list.
- `check_platform_first.py --self-test` mutates its own rule table (removes a deny rule)
  and fails; it deletes a wiring entry and fails — a gate that proves it can fail.
- The three copies of the rules engine (the repo hook, the `awsettings`-distributed
  guard, the public twin) are byte-identical under the same parity gate that already
  guards the delivery homes (HYG005); drift is loud, not silent.
- `awkno law 32` and `awkno -k hand-roll` answer offline with no code change (the codex
  globs this directory).
