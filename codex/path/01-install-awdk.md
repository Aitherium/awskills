# Install awdk — one command, then proof it worked

*Chapter 1 of 9 · about 10 minutes · you need: a terminal and an internet connection*

## Teach

### What you are installing

**awdk** — *Aither World Dev Kit* — is one program with many verbs. Everything in
this guide runs through it: starting a brain (`adk quickstart-local`), chatting
(`adk chat`), building an agent (`adk init`), installing packs (`adk install`). One
install, and the rest of the chapters are verbs of the same command.

The command is called `adk`. Short for *agent dev kit*; it is the same thing.

### What "pip" is

Most of the kit is written in Python, and `pip` is Python's installer — the way
`apt` installs on Ubuntu or the App Store installs on a phone. `pip install awdk`
downloads the kit from PyPI (the public Python package index) and puts `adk` on your
PATH, which is the list of folders your terminal searches when you type a command.

That last part matters: a terminal reads PATH when it *opens*. If `adk` is "not
found" right after installing, the window you are in is simply older than the
install. Open a new one.

### What the wizard does

`adk wizard` asks a handful of questions and writes one small config folder in your
home directory, `~/.aither/`. Pressing Enter accepts every default, and the defaults
are right for this guide. It changes nothing else on your machine.

### What the doctor does

`adk doctor` is a list of checks, one per line, each ending in **OK**, **WARN** or
**FAIL**. It does not guess; it tries the thing and reports. Any time something is
odd later in the guide, this is the first command to run. A **WARN** about not being
logged in is expected — we do that in chapter 3, and only if you want to.

## Do

Type each line, press Enter, and compare with what you should see.

**1. Install**

```bash
pip install awdk
```

You should see: `Successfully installed awdk ...` (a version number follows).

If `pip` is not recognised: install Python from python.org — on Windows, tick
**Add python.exe to PATH** on the first screen — then open a *new* terminal and try
again.

Prefer a one-liner that also installs Python for you?

```bash
# macOS / Linux
curl -fsSL https://aitherium.com/install.sh | sh
```

```powershell
# Windows
irm https://aitherium.com/install.ps1 | iex
```

**2. Set up**

```bash
adk wizard
```

You should see a short questionnaire. Press Enter for each default.

If `adk` is not recognised: close this terminal, open a new one, try again.

**3. Check**

```bash
adk doctor
```

You should see a list of checks ending in **OK**. One **WARN** about cloud login is
fine.

If a line says **FAIL**: read that line — it names the fix. Nothing below it matters
until it is green.
