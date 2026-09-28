# Set up Claude Code the Aither way — the bricks as tools, the settings in the right scope

*Chapter 11 · about 10 minutes · you need: chapter 1 finished, Claude Code installed*

## Teach

### One command instead of an afternoon of settings

Claude Code can use every aw* brick you already have: as MCP servers it calls, as skills it
loads when the task matches, and as hooks that run around each turn. Wiring that by hand
means editing several settings files and getting each one's scope right. `adk claude setup`
does it in one step, and `adk claude doctor` tells you whether it is still true next week.

### Which file a setting lives in matters

Claude Code reads settings from several layers: your user folder, the project, and a
machine-local file next to it. A setting written to a layer that does not honour it is
ignored without an error — it just does not exist
([law 25](https://github.com/Aitherium/awknowledge/blob/main/laws/25-a-setting-in-a-scope-nobody-reads-does-not-exist.md)). Setup writes
the permission mode to your *user* settings only, never to a repository other people clone.

### What travels and what stays

Presets and files travel between your machines; credentials never do
([law 29](https://github.com/Aitherium/awknowledge/blob/main/laws/29-portable-is-files-and-presets-never-credentials.md)). Setup keeps the
two apart, so syncing your settings to a second machine never copies a token.

### Hooks cost time on every call

A hook runs on every tool call, so a slow one slows everything
([law 26](https://github.com/Aitherium/awknowledge/blob/main/laws/26-a-hook-on-every-call-spends-a-latency-budget.md)). The hooks setup
installs check cheaply first and only do real work when the call is one they care about.

## Do

```
adk claude setup
adk claude doctor
```

`doctor` reads what Claude Code will actually load and names each thing that drifted. Run it
again after you upgrade Claude Code or awdk, and whenever a tool you expect is missing.
