# Build a pack — give every agent a new skill

*Chapter 10 · about 20 minutes · you need: chapter 5 finished, a terminal*

## Teach

### A pack is a folder

In chapter 5 you installed a pack someone else built. This chapter is the other side: you
write one. A **tool pack** is an ordinary folder with three things in it:

- `.toolpack.yaml` — the manifest: an id, a version, a one-line description
- `__init__.py` — a `register(registry)` function that hands your tools to the agent
- `tools.py` — the tools themselves, plain Python functions

The docstring and the type hints of each function ARE what the agent reads to decide when to
call it, so write them for the model: say what the tool returns and when it is the right one.

### Your id is your namespace

Pack ids look like `yourname.weather`. The part before the dot is yours; names that start
with `aither` or `adk` belong to the platform and are refused, so a community pack can never
shadow one the platform ships.

### Four verbs, one loop

`adk pack` has four author verbs, and each one answers a single question:

| verb | question it answers |
|---|---|
| `new` | what does a working pack look like? |
| `validate` | is the folder correct — without running any of its code? |
| `dev` | does it load the way an agent will load it, and which tools does it expose? |
| `build` | what exact bytes am I publishing? |

`validate` never imports your code, so you can run it safely on a pack you downloaded from
a stranger. It also looks for anything shaped like an API key and reports the file and line
without printing the value. `dev` is the one step that runs your code, and it says so.

### Reproducible bytes

`build` writes a `.tar.gz` and its sha256. The archive has sorted entries and zeroed
timestamps, so the same source always produces the same bytes. Anyone who rebuilds your
tagged source gets your digest, which is how a stranger can trust a pack they did not write.

## Do

**1. Create a pack**

```bash
adk pack new yourname.weather
```

You should see: `created` and the path of a new `yourname.weather` folder, then the next
two commands to run.

If it says the id is reserved: pick a namespace of your own, like your GitHub handle.

**2. Validate it**

```bash
adk pack validate yourname.weather
```

You should see: `OK yourname.weather 0.1.0` and `all clean`.

If it lists a `PKA` code: each one names the file or field to fix. Fix it and run the
command again.

**3. Load it like an agent would**

```bash
adk pack dev yourname.weather
```

You should see: `OK yourname.weather: 1 tool(s) registered` and the tool name
`weather_echo`.

If it says 0 tools: open `__init__.py` and check that `TOOL_NAMES` lists the functions in
`tools.py`.

**4. Build what you will publish**

```bash
adk pack build yourname.weather
```

You should see: `built` with the path to `yourname.weather-0.1.0.tar.gz`, and a `sha256`.

Now make it yours: replace `weather_echo` in `tools.py` with a real tool, bump the version,
and run the four commands again. To share it, push the folder to a public repository and
attach the tarball and its `.sha256` to a release. Anyone can install it by unpacking the
folder into `~/.aitheros/packs/`.
