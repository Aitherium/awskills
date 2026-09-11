# A cap that does not survive a restart is not a cap — the persistence law
*Part VI · Configuration*

**Fires when:** you set a resource limit, a quota, a timeout, a priority, or a
binding that you intend to survive a restart.

## The law

A configuration change on a running process that does not also change the
declaration that recreates it is a patch, not a fix. It lives until the next
restart. **After the restart, the process returns to what its declaration says.**

This is straightforward for files. It is invisible for runtime properties because
the process looks correct while it is running, and nothing announces the moment it
reverts. The cap looks live, the healthcheck is green, the cheap checks all pass.

**You have configured the running instance, not the system.**

## Why this matters for availability

A runtime limit that protects you from an outage only protects you **until the
next restart**. A restart can happen for reasons you did not choose:

- Auto-healing (e.g. a container restart after memory pressure)
- A routine rolling restart
- An unrelated service restart that cascades
- An owner-commanded rollout
- A system update
- Infrastructure failure and recovery

After any of these, the limit evaporates and the outage returns. If the limit was
protecting you from a boot deadline (WSL's 10-second systemd timeout) or a resource
starvation loop, the system enters the same failure mode again — often while
everyone is asleep.

**The outage you fixed has not been fixed. It has been paused.**

## The four gaps this guards against

**1 · Forgetting to persist.** You notice a problem, `podman update --cpus 4
container-name` fixes it immediately, load falls, you document it in a ticket, and
move on. The ticket sits. Four weeks later a deployment rolls and the container
restarts with no cap, and the same outage returns while you are debugging
something else. The fix was applied.

**2 · A temporary setting becoming permanent.** A debugging flag, a reduced
timeout, or a lowered limit was set to diagnose an issue. It is no longer needed.
But nobody found where it was declared — it only exists on the running instance
— so it stays. Six months later a restart lands it on a second production server
and breaks something that was never broken on the first.

**3 · Disagreement between the two sources of truth.** The unit file says one
thing; the running container says another. The process respects the running state
(correctly). A new person joining the team reads the unit file and assumes that is
what is running. They think the fix was already applied. They think the problem is
something else.

**4 · A cap that is starving the service.** The cap was set because the system
needed bounding. But the bound was too aggressive. The running process reports
throttle events, reports stalls, or serves requests slowly — all of it invisible
to a healthcheck. The limit is necessary (otherwise the boot deadline fails), but
its value was never validated on a real workload. Every time the service restarts
it suffers until someone notices and adjusts it — always after an outage.

## The check

Before claiming a configuration change is live, verify **both**:

```bash
# 1. Is the running process in the desired state?
<engine> inspect <container> --format '{{.State | json}}' | grep -i cpus
# (or the property you set)

# 2. Is that property DECLARED in the unit that will recreate it?
grep -i cpus <quadlet_file>  # or the equivalent for your engine
```

If (2) is absent or disagrees with (1), the change is temporary, not persistent.
Applying it to the declaration is the fix.

## The operational form

A persistently-limited container must express its limits in its **unit
declaration** — the quadlet, the compose file, the deployment spec, or the
equivalent for your engine. A limit that lives only in the running process
invites a silent regression on the next restart.

When you fix something this way, state both the **current state** (what the
process is doing today) and the **declared state** (what it will do after a
restart). If they differ, the fix is incomplete.
