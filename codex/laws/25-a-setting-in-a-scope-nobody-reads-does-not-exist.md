# A setting in a scope nobody reads does not exist — know which layer the harness honours
*Part VI · Configuration*

**Fires when:** you grant an agent a permission, a sanction or a mode by writing a key into
a settings file; when a harness offers several settings layers (managed, user, project,
local) and you pick the one closest to the work.

## The law

Layered settings are not one namespace. Each key is read from the layers the harness
chooses for it, and a key written anywhere else is **silently ignored** — no warning, no
error, the file still parses, and the agent behaves exactly as if you had never written it.

The keys that matter most are the ones most likely to be scoped away: anything that widens
what an agent may do. Claude Code reads its `autoMode` block **only** from user or managed
settings. The same block in project or local settings is dead, and it looks alive because
it sits next to keys (permissions, hooks) that the project layer *does* honour.

## The check

- For every sanction-shaped key, record which layers the harness reads it from, and assert
  that the key lives in one of them. A check that parses the file is not enough — it must
  know the layer.
- Prove it from behaviour, once: set the key, start a fresh session, and observe the
  change. A key you cannot observe taking effect is a key you have not set.
- When a key moves layers, delete the dead copy. Two copies, one live and one ignored,
  is how the next reader edits the wrong one.
