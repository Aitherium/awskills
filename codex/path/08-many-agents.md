# Many agents, one repo — leases, a call graph, messaging, memory

*Chapter 8 of 9 · about 30 minutes · you need: a git repository and a terminal*

## Teach

### Two agents, one file

When two agents edit the same code, they can overwrite each other's work. Git tracks which *lines* changed, but it doesn't know that agent A is editing a function and agent B is reindenting it — it just sees lines moving, and when both agents commit their changes, the merge becomes a puzzle Git cannot solve alone. A **lease** stops this: before you edit a file, you claim it for a time period. If someone else holds the lease, you know to stay out; if you crash, the lease expires and the file becomes editable again.

### Looking without reading everything

An agent needs to know who calls a function, what it calls, and what tests cover it — the relationships that decide which files matter to a change. A **call graph** indexes the repository by parsing it into symbols, calls, and callers, so you can answer "who calls main" without reading every file that matches the name. The index is built once and cached on your machine, not downloaded.

### Talking through a channel

An agent that finds a bug has nowhere to tell another agent except its own transcript, which nobody reads. A **relay** is a chat channel a human can read, where agents leave findings, alerts and coordination messages in a format humans can read and agents can parse. Because the channel is durable and searchable, a decision made there is not relitigated when the next agent hits the same symptom.

### Learning without re-learning

Memory lets an agent record something it learned — a recipe, a decision, a measurement — so the next agent doesn't have to re-derive it. **awm** stores it in scopes so an agent's learning stays in the right context: a project-level recipe is not written to the platform, and your personal preferences do not crowd out shared ones.

## Do

Type each line, press Enter, and compare with what you should see.

**1. Install four bricks**

```bash
pip install awgit awgraph awrelay awm
```

You should see: `Successfully installed awgit awgraph awrelay awm ...`

If it fails on one: install them one at a time to see which — each is independent of the others.

**2. Claim a file**

```bash
awgit lease acquire README.md
```

You should see: a lease on the file, with its holder and an expiry time.

If the command is not found: run it inside a git repository. A lease is about a file in a repo.

**3. Query a call graph**

```bash
awgraph query "who calls main"
```

You should see: a list of callers, or `no index yet — run the command it prints`.

If you see the latter: build the index first — `awgraph index .` — then query again. The graph is derived from your code, not downloaded.

**4. Send a message**

```bash
awrelay send "#general" "hello from the guide" --kind note
```

You should see: message delivered, with the channel name and a message id.

If `RelayError`: awrelay needs a relay endpoint. The error names which one is missing: a URL in an environment variable, or a relay server from chapter 3's login.

**5. List your leases**

```bash
awgit lease list
```

You should see: the lease you took in step 2, still held.

If it is expired: leases run for one hour by default. Take a new one and the clock resets.

## Learned

- A lease says "I am editing this" and it expires — so a crashed agent cannot lock a file forever.
- A call graph is the answer to questions you would otherwise answer by reading the whole tree.
- Messages between agents go through a channel a human can read too. That is how a decision found once reaches the next agent who needs it, without relitigating it again.
- The laws that made awgit, awgraph, awrelay and awm necessary are documented at Reference › Laws — read "Design for the silence" and "The defect lives in the union" to see why each one exists: every one was a real failure in the wild first.
