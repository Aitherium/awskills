# Portable is files and presets, never credentials — split what travels from what stays
*Part VI · Configuration*

**Fires when:** you package an agent setup for another machine or another person — a
plugin, a settings preset, a dotfiles sync, a "set it up the way I have it" command.

## The law

An agent setup is three different things that only look like one file:

| kind | what it is | how it travels |
|---|---|---|
| **content** | skills, rules, hooks, commands, agents | a plugin or package — files, versioned |
| **preferences** | model, voice, notifications, UI keys | a settings preset — merged into the user layer, never overwriting |
| **machine-local** | credentials, tokens, absolute paths, and the environment an owner's sanctions describe | **never travels** |

Mixing them is how a shared preset ships a token, or an owner's description of their own
environment becomes every recipient's standing grant. The sanction itself is trust the
owner gave for one machine; copying it is granting it to a stranger.

## The check

- The export path has a denylist for machine-local keys and a scan for secret-shaped values
  and absolute paths; it fails on a hit rather than redacting silently.
- The import path refuses the same keys (law 28).
- A setup command applies content and preferences, then **asks** for anything machine-local
  instead of copying it.
