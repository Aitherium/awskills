# Your first local brain — an open model on your own computer, offline

*Chapter 2 of 9 · about 20 minutes · you need: chapter 1 done, ~6 GB of free disk, a few minutes of download*

## Teach

### What a model is

A language model is a very large file of numbers — billions of them — and a
program that uses those numbers to turn text in into text out. That is the whole
thing. When people say "the AI", they mean the numbers plus the program that runs
them. Running it is called **serving**: the program loads the file into memory and
waits on a port (a numbered door on your machine) for questions.

Think of a vinyl record and a turntable. The record is the model; the turntable is
the server; the music only exists while both are together. The record is useless on
its own, and the turntable plays whatever you put on it.

### What "8B" means

"8B" is eight billion numbers. Each number normally takes 16 bits, so an 8B model is
about 16 GB — too big for most laptops' memory. **Quantization** stores each number
in fewer bits. At 4 bits the same model is ~4.5 GB and almost as good. At **1 bit** —
which is what Bonsai does — a 27-billion-number model fits in 3.8 GB and runs on a
plain CPU with 8 GB of RAM.

Fewer bits is a trade: smaller and faster, very slightly less precise. The kit picks
the trade that fits your machine, so you do not have to.

### The open model stack

Two families of brains are Aitherium's own, and both are open:

- **The orchestrator model** — the open 8-billion-parameter brain the platform itself runs
  on. This is the one `adk quickstart-local` downloads for you (an openly published
  GGUF file, quantized to fit your RAM).
- **Bonsai** — the 1-bit family from PrismML. Bonsai-27B is the "big brain in a tiny
  box" option, and because 1-bit files need a special version of the server, the kit
  ships it as a container (`adk bonsai-local`, optional below).

Open means: the file is public, you can download it, and nothing about it phones
home. Unplug your network after this chapter — it still answers.

### What `quickstart-local` does, step by step

It prints five steps as it goes:

1. **Detects your hardware** — CPU or GPU, how much memory.
2. **Picks a backend** — the program that will serve the model: plain `llama.cpp`
   on a CPU (no dependencies), Ollama if you already have it, vLLM on an NVIDIA card
   with Docker.
3. **Installs it** and downloads a model sized for you. This is the slow step.
4. **Verifies** it by asking the model a question and checking an answer comes back.
   A failed check fails the command — "quickstart" means *proven working*.
5. **Registers** the brain with the kit, so every later chapter can find it.

## Do

**1. Start a brain**

```bash
adk quickstart-local
```

You should see: `[1/5] Detecting hardware...` through `[5/5]`, then an address like
`http://localhost:8200/v1`, then `Config saved:`. The first run downloads several
gigabytes; later runs are instant.

If step 3 fails to download: check you have ~6 GB free and run the same command
again — the download resumes where it stopped.

If it picked Ollama and you did not expect that: you already had Ollama installed,
and that is fine — it is a good backend.

**2. Optional — the 1-bit brain**

```bash
adk bonsai-local
```

You should see: `Starting Bonsai-27B ...` and then a healthy endpoint on port
8090. The first time, it builds the container on your machine — PrismML's
llama.cpp fork plus the 3.8 GB weights, fetched from their public sources — which
can take up to ~40 minutes once. After that it starts in seconds.

If it says Docker is not found: skip this step. It needs Docker Desktop, and the
brain from step 1 is already running. Come back for Bonsai whenever you like.

**3. Check you are done**

```bash
adk backend status
```

You should see: `Backend: llamacpp` (or `ollama` / `vllm`), an `Endpoint` on
localhost, and the model name from step 1.

If it says not configured: step 1 did not finish. Run it again and read the step
that stops.
