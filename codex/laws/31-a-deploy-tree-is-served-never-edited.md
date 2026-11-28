# A deploy tree is served, never edited — change it through a commit, and let the sync never stall
*Part IV · Deployment*

**Fires when:** a checkout is bind-mounted into containers, runs an editable install, or
is moved to the branch tip by a sync lane — and an agent or a person is about to edit a
file in it.

## The law

A checkout that something serves is a deploy target, not a workspace. An edit made there
skips review, never reaches the branch, and sits in front of the next deploy: when the
sync lane meets a file that both the branch and the hand edit changed, it must either
destroy the edit or stop. Stopping is correct for one file and ruinous for a habit.

Measured 2026-11-11: dozens of sessions edited the live AitherOS tree in place and left
5,522 uncommitted files with no owner. 282 of them collided with merged work, the sync
refused, and the tree sat 2,753 paths behind develop for days — nothing merged in that
time was live.

Close it from both sides:

1. **Refuse the edit at the door.** Mark the tree (`awgit deploy-tree mark`); a PreToolUse
   hook (`awgit deploy-tree guard`) denies Edit/Write into it and names the fix,
   `awgit wt new <name>`.
2. **Never let the sync stall.** What still lands there by other means is committed to a
   pushed `rescue/deploy-tree/<ts>` branch, announced, and then the tree moves. A stray
   edit can delay a deploy by one run, never by days, and it is never lost.

## The check

- `awgit deploy-tree status` on the served tree: marked, and the dirty count trending to 0.
- The sync runs on every merge, and a run that rescues files says which and where.
- A test plants an uncommitted edit on a path develop changed and asserts the sync
  pushes it to a rescue branch, then moves the tree; a second asserts an unpushable rescue
  refuses and changes nothing.
