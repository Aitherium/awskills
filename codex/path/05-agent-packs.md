# Agent packs — a whole agent in one command

*Chapter 5 of 9 · about 15 minutes · you need: chapter 4 finished, a terminal*

## Teach

### What a pack is

A **pack** is an agent you did not write. Someone — maybe Aitherium, maybe another user — built a complete agent with brain settings, tools, and a job, and published it so you can have it in one line.

You already met packs: Bonsai in chapter 2 is a pack (it comes as a container), and the "tools" chapter 4 talks about are tools that packs bring with them.

### The pack you will try

OpenClaw is a research agent — it searches the web, gathers sources, cites them, and builds a knowledge graph so you can ask follow-up questions and it remembers context across them. Research agents without your own tools are useful, but the ones with tools are agents: they can *act* (search, retrieve, synthesize) instead of just guessing.

### Where packs come from

Right now, packs ship inside awdk. When you `pip install awdk`, you get a bundled catalog of packs — free ones like the Orchestrator, and paid tiers like Hydra (testing and QA). The packs live inside the kit.

The **awpack** public registry is being built. When it ships, this page will change to "go to the marketplace, browse, pick one, install". Until then, the bundled set is what you have.

### The difference between packs and skills

A **skill** is smaller — one procedure. Research a question, send an email, approve a decision. Skills live in **awskills** (https://aitherium.github.io/awskills/) and are used by agents to do specific jobs. A pack is a whole agent; a skill is one thing an agent can do. Think of a pack as a person and a skill as a technique that person knows.

## Do

**1. List the packs**

```bash
adk packs
```

You should see: a table of packs with a name and a one-line purpose.

If you see an empty table: `pip install --force-reinstall awdk` restores the bundled catalog.

**2. Install one**

```bash
adk install pack:openclaw
```

You should see: `Installing openclaw...`, then `Installed to:` a folder in your home directory, and `Next steps`.

If the name does not match: run `adk packs` again and copy a name exactly — it is case-sensitive.

**3. Run it**

```bash
adk run --agents openclaw
```

You should see: `Starting AitherADK fleet server — agents: openclaw, port: 8080` —
the pack's agent is now serving. Ctrl+C stops it.

If port 8080 is busy: add `--port 8081`. If it says the agent is unknown, the
install step did not finish — read its last line.

**Done?**

```bash
adk run --agents openclaw
```

You should see: `Starting AitherADK fleet server — agents: openclaw`.
