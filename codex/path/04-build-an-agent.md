# Build your first agent — a brain plus tools plus a job

*Chapter 4 of 9 · about 30 minutes · you need: chapter 3 done, any text editor*

## Teach

### What makes an agent an agent

A brain answers. An **agent** acts. The difference is tools: functions the brain
is allowed to call, and a loop that lets it call one, look at the result, and
decide what to do next. Give a brain tools and a job, and it can check the time,
read a file, search, send a message — and *then* answer.

Think of a new employee. The brain is what they know; the tools are the badge,
the phone and the filing cabinet; the job is the one-page description you hand
them on day one. Chapter 3 was a conversation with someone who has no badge.

### The three files

`adk init` writes a folder with three files, and they are the whole agent:

- **agent.py** — the agent itself: about twenty lines that create it, give it
  one tool, and ask it a question. Read it; it is shorter than this page.
- **config.yaml** — its settings: a name (`identity`), which brain to use
  (`llm_backend: auto` means "whatever chapter 2 set up"), a port, and which
  packs to load.
- **tools.py** — your own tools. Two examples are already there.

### What a tool is

A tool is an ordinary function with a decorator on top:

```python
@agent.tool
def hello(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"
```

The decorator registers it with the brain, and the docstring is what the brain
reads to decide *when* to use it — so write the docstring for the brain, not for
you. Nothing else changes: it is still a Python function you can call yourself.

### Two ways to run it

**Once.** `python agent.py` creates the agent, asks it the question written at
the bottom of the file, prints the reply, and exits. This is how you try a change.

**As a service.** `adk run` keeps the agent listening on a port so other
programs can talk to it — the web, other agents, and the packs in chapter 5. You
do not need it yet; it is here so the word "server" is not a surprise later.

## Do

**1. Scaffold**

```bash
adk init my-agent
```

You should see: `Created AitherADK project at my-agent/`, the three files named,
and `Next steps`.

If it says the folder exists and is not empty: pick another name. `init` never
overwrites.

**2. Go inside**

```bash
cd my-agent
```

**3. Run it once**

```bash
python agent.py
```

You should see: one greeting, printed by your agent. (`agent.py` asks it to say
hello to the world, and the agent has a `hello` tool to do it with.)

If it cannot reach a brain: `adk backend test` tells you whether chapter 2's
brain is up. If `python` is not found, try `python3`.

Now open `agent.py`, change the question at the bottom, run it again.

**4. Optional — run it as a service**

```bash
adk run
```

You should see: `Starting AitherADK server — identity: my-agent, port: 8080`,
and then it keeps running. Ctrl+C stops it.

If port 8080 is busy: `adk run --port 8081`.
