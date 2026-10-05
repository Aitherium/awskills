# A guard in one direction is half a guard — refuse inbound what you strip outbound
*Part V · Trust*

**Fires when:** you write a sync, an export, a mirror or a publish step that filters out
sensitive keys, paths or content on the way out.

## The law

A filter that removes secrets, sanctions or machine-local state when **pushing** protects
only the machine it runs on. The same sync **pulling** from a shared store will happily
write whatever that store holds — a hand-edited file, an older client that never filtered,
an attacker who can write the store. The dangerous key arrives through the door you
thought you had closed.

If a key is unsafe to send, it is unsafe to receive. Enforce the rule on both edges with
the same list, and make the inbound edge **refuse loudly** rather than silently drop, so a
poisoned store is seen instead of papered over.

## The check

- One denylist, imported by both the push and the pull path — never two copies.
- A test that plants each denied key in the shared store and asserts the pull refuses it,
  alongside the test that asserts the push strips it.
- The pull's refusal names the key (never its value) and exits non-zero.
