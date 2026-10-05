# Talk to it — one question, then a conversation

*Chapter 3 of 9 · about 15 minutes · you need: chapter 2's brain running*

## Teach

### A prompt is a request, not a command

When you type to a brain you are not giving an instruction a computer obeys; you
are handing over a request it interprets. Two things follow. First, *how* you ask
changes what comes back — a vague question gets a vague answer, and "explain it
like I have never seen a terminal" genuinely works. Second, the brain knows only
what it was given: the model file and your message. It cannot see your files,
your calendar, or the time unless something hands those to it. Chapter 4 is
about handing things to it — that is what tools are.

### Two ways to talk

**One question.** `adk backend test` sends a single fixed prompt to whatever brain
the kit is pointed at and prints the reply with the provider, the model and a
token count. It is the smoke detector: if this says `Status: OK`, everything
above it in the stack is fine.

**A conversation.** `adk start` opens a chat. Run it inside a folder and it also
reads that folder — Python files get indexed — so you can ask "what does this
project do?" and get an answer grounded in what is actually there. The banner at
the top tells you which brain it found. Type `/quit` to leave.

### Local or cloud is per task, not forever

Everything so far runs on your machine with no account. Aitherium also hosts
bigger brains, and `adk login` connects you to them. It is optional in this
guide, and it stays optional: every later chapter works offline.

If you do log in, notice what does *not* happen: you never type a password into
the terminal. The kit prints a short code and a web address; you open the page,
type the code, and come back. That is a **device code** login — the same thing a
TV does when you sign in to a streaming app — and it means the terminal never
holds your password at all.

`adk whoami` tells you which state you are in. Both answers are fine.

## Do

**1. One question**

```bash
adk backend test
```

You should see: `Provider: …`, a one-line `Response: …` from your brain, and
`Status: OK`.

If it says FAILED: the brain from chapter 2 is not running. `adk backend status`
shows what the kit expects to find; `adk quickstart-local` restarts it.

**2. A conversation**

```bash
adk start
```

You should see: a small banner — Workspace, Directory, `LLM:` naming your local
brain and its address — then a `You >` prompt. Ask it something. Type `/quit` to
leave.

If the LLM line names the cloud, or says nothing was found: the local brain is
down — see step 1.

**3. Optional — connect to the cloud**

```bash
adk login
```

You should see: a short code and a URL. Open the URL, type the code, come back:
`Logged in as …`.

```bash
adk whoami
```

You should see: your account, or `Not logged in`. Either is fine.
