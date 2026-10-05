# Your own hardware — CPU, GPU, laptop, rack

*Chapter 6 of 9 · about 30 minutes · you need: chapters 2 and 3 done, a terminal*

## Teach

### How the kit picks a brain for your machine

Chapter 2 ran a brain on your CPU or GPU. But how did the kit know which one you had? And how big a model is safe for your RAM?

The kit **measures your hardware** — how much RAM, whether you have a GPU, whether Docker is running — and picks a model and a backend that fit. An 8B model needs at least 8 GB of RAM (or VRAM); Bonsai's 1-bit family fits in less. vLLM on NVIDIA is faster than llama.cpp on a CPU. The kit makes that choice so you do not have to know the numbers.

### Model size and memory

A **model** is numbers — weights. An "8B model" has 8 billion of them. A 4-bit quantization stores each in 4 bits instead of 32, so it fits in 8× less memory. This is why quantization exists: the same brain in a smaller space.

- **The orchestrator model** is the open 8-billion-parameter brain the platform itself runs on. It is a good default.
- **Bonsai** is the 1-bit family — Bonsai-27B is 27 billion parameters in 3.8 GB. It fits on a machine with 8 GB of RAM and runs on a CPU. It is the brain for tiny machines.

### What a backend is

A **backend** is the software that loads and runs a brain. llama.cpp runs models on CPUs and small GPUs. vLLM runs them on NVIDIA with high throughput. Ollama is a middle ground — easy to use, a bit slower.

Registering a backend is what lets agents anywhere reach it. A brain nobody registered is a brain nobody can call. `adk backend status` tells you which brain the kit is pointed at. `adk up` registers this machine as a service.

## Do

**1. Detect and set up**

```bash
adk quickstart
```

You should see: hardware detected, a recommended setup, and a running backend.

If you see "no GPU": this is the same as chapter 2 — the kit picked llama.cpp on your CPU. On NVIDIA with Docker, it will offer vLLM.

**2. See which brain the kit is pointed at**

```bash
adk backend status
```

You should see: `Backend`, `Endpoint` and `Model` — the brain the kit is currently using.

If it says not configured: chapter 2 did not finish. Run `adk quickstart-local` first.

**3. Register it (optional)**

```bash
adk up
```

You should see: your agent deployed as a service on this box, enrolled with your workspace, heartbeat every 60 s.

This needs a login from chapter 3 and Docker. Without either, `adk run` from chapter 4 is the offline equivalent — your agent runs on your machine but does not register anywhere.

**Done?**

```bash
adk backend status
```

You should see: the backend you chose, with an Endpoint that answers.
