# A hook on every call spends a latency budget — prefilter before you import
*Part VII · Scaling*

**Fires when:** you wire a hook that runs before or after every tool call, every shell
command or every prompt; when an agent session "feels slow" and nothing is obviously busy.

## The law

A hook that fires on every call is paid on every call, serially, for the life of every
session. Its cost is not "small" — it is its median latency multiplied by the number of
calls, and a busy agent makes thousands. Interpreter start-up and module imports dominate
that cost long before the hook's own logic runs.

So the shape is fixed: **decide whether the call concerns you before you import anything.**
Read the event, match it against a cheap string or pattern test, and exit immediately on
the common case. Only the rare call that matches pays for the heavy path.

## The check

- Measure the median and the tail (p95) in milliseconds for the no-match path and the match
  path separately, on real events, and write both numbers down beside the hook.
- Give the no-match path a budget and a test that fails when a new top-level import
  pushes it over. Imports creep; a budget nobody asserts creeps with them.
- Several hooks on the same event are one budget, not several. Merge them behind one
  prefilter rather than paying start-up once per hook.
