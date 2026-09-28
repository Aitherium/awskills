# Welcome to Aither World — what this is, before you install anything

*Chapter 0 of 9 · about 5 minutes · no computer needed yet*

## Teach

### Three words you will see everywhere

**Aitherium** is the company and the platform: the hosted service at aitherium.com,
the accounts, the marketplace, the people.

**AitherOS** is the operating system underneath it — not a Linux you install, but the
running fleet of services that gives agents memory, identity, tools and a place to
talk. You never have to run AitherOS yourself. Everything in this guide works on your
own laptop; the platform is there when you want more.

**aw** is short for **Aither World**. Every tool in the family is named as a phrase:
`awdk` is *Aither World Dev Kit*, `awnix` is *Aither World Nix* (a Linux), `awsh` is
*Aither World Shell*. If a name does not read aloud as "Aither World <something>", it
is not one of ours. We call each of these tools a **brick** — small, standalone, and
useful on its own before it is useful together.

### What an agent actually is

A chatbot answers. An **agent** *acts*: it can run a command, read a file, search the
web, send a message, and then decide what to do next based on what happened. The
difference is tools. Give a brain tools and a job, and you have an agent.

So an agent is three things:

- a **brain** — the model that reads and writes language;
- **tools** — functions the brain is allowed to call;
- a **job** — what it is for, written down in a small file.

Chapter 4 has you write that file. It is shorter than this page.

### The brains are open

Aitherium's own brains are open models you can download and run:

- **The orchestrator model** — an open 8-billion-parameter model the platform itself runs on.
  It fits on an ordinary laptop.
- **Bonsai** — a family of models squeezed to about *one bit per weight*. Bonsai-27B is
  a 27-billion-parameter brain in 3.8 GB, and it runs on a plain CPU with 8 GB of RAM.

"Open" means the numbers that make up the model are published. You can run them
with no account, no network, no bill. Chapter 2 does exactly that.

### How this guide works

Every chapter from here on has two columns. **Teach** (left) explains what a thing
is and why it exists, in plain words. **Do** (right) is the exact command to type,
what you should see, and what to do if you do not see it. Every chapter ends with
one command that proves you finished.

You never need a later chapter to do an earlier one. If you stop after chapter 3 you
have a working local brain you can talk to, and that is a fine place to stop.

## Do

Nothing yet. Find your terminal:

- **Windows** — press the Windows key, type `terminal`, open *Terminal* (or *PowerShell*).
- **macOS** — press Cmd+Space, type `terminal`, open *Terminal*.
- **Linux** — you already know.

Leave it open. Chapter 1 starts there.
