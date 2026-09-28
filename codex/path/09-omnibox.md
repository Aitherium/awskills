# The omnibox — your terminal answers you

*Chapter 9 of 9 · about 10 minutes · you need: a terminal and Node.js 18 or newer*

## Teach

### The shell's one answer

A shell has exactly one response to a line it doesn't recognize: `command not found`. So every time you want to look something up — what is the hash of this commit, what does this API need, how does time work on this machine — you leave the terminal and reach for a browser, losing the directory, the environment and the session you were in. The omnibox makes that line reach an agent instead, so you stay.

### It is a hook, not a new shell

This is not a new shell language. It is a **hook** that installs into your existing shell — PowerShell, bash or zsh — so your terminal stays your terminal. Your directory, your environment variables, your history, the session you are in: they are all still there. The omnibox just intercepts the moment before `command not found` and asks an agent instead.

### Scripts stay silent

Every script tests whether a tool is installed by running `get-command <name>` or `which <name>`. Without a guard, every test would fire an agent request, invisibly, and those requests would be billed. So the hook fires only on lines a human types at the prompt — not on probes made from inside a script or function. A tool check returns `command not found` the normal way; your question typed at the prompt gets an answer.

## Do

Type each line, press Enter, and compare with what you should see.

**1. Install the shell**

```bash
npm i -g @aitherium/awsh
```

You should see: `awsh and aither on your PATH` (the commands are installed).

If `npm` is not found: install Node.js from nodejs.org (LTS version). Then open a **new** terminal and try again.

**2. Wire the hook**

```bash
awsh init
```

You should see: `installed in <your shell profile path> — it works in PowerShell, bash and zsh`.

If the profile is not writable: the output will print the exact line to add by hand. That single line is the whole feature.

**3. Check the performance**

```bash
awsh doctor
```

You should see: a measured miss time, well under the budget it prints.

If the miss time is slow (over 100ms): it names the PATH entry causing it — usually a large directory on `PSModulePath`. Remove that entry from your profile; it is costing every typo you make a minute.

**4. Ask the terminal**

```bash
what time is it
```

You should see: an answer — the time, or today's timezone, or a sentence about how to check it.

If you see `command not found` instead: open a **new** terminal — the hook installs into the shell profile, and the profile loads when the terminal starts.

## Learned

The shell has exactly one default response to a line it doesn't know. Now that line reaches an agent. You stay in your terminal, in your working directory, with your environment — and the answer comes back where the error used to be. It is a shell hook (CommandNotFound for PowerShell, command_not_found_handle for bash), so only what you type at the prompt gets answered. Scripts test for tool existence the usual way and stay silent. You have installed a complete kit (chapters 1–7), built an agent (chapter 4), wired it into your own hardware (chapter 6), and now your terminal talks back. Type a question at any prompt and get an answer, and the agent you trained will be the one answering.
