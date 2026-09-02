# awembed — train an embedding model that knows your corpus

Your agents search your code, your docs, your tickets with an embedding model that has
never seen any of it. A general-purpose embedder is right about two thirds of the time
on a corpus it was not trained on. You can do better with a model thirteen times smaller,
in an afternoon, on one GPU — and prove it on a split the model never saw.

Measured on one codebase: the distilled 0.6B student retrieved the right directory on the
first try 80% of the time; the 7.85B teacher it learned from managed 66%; the same 0.6B
model before training, 62%. The student ships as 1.06 GB of int8 at 0.999 fidelity.

## Why a small model wins here

The student is trained on two signals at once. The **teacher's margins** — how far it
separates the right answer from plausible wrong ones — is the distillation half. The
**corpus's own labels** — which document actually answers which question — is the
in-domain half, and it is the one the teacher never had. For retrieval over something
you own, in-domain supervision is worth more than parameters.

## Install

```bash
pip install awembed              # student side (torch + transformers)
pip install "awembed[teacher]"   # also the teacher server
```

## The recipe, stage by stage

Every stage writes a sidecar with what it measured and refuses to hand on an artifact
that fails its gate. Run them in order against one output root.

```bash
# 0. Corpus: one row per question -> right document -> K hard negatives (plausible and
#    wrong). Split by DIRECTORY so eval never sees a directory training saw.
awembed corpus --root /path/to/repo --out corpus.jsonl

# 1. Prove the teacher loads and answers on THIS machine before you rent anything.
awembed probe          # exit 0 ok / 1 failed / 2 could not judge

# 2. Capture: score every row with the teacher (starts the teacher server for you).
awembed capture  --corpus corpus.jsonl --seed 1 --out artifacts/

# 3. Distill the student. Gate: the loss must fall (last-10 mean < first-10 mean).
awembed distill  --corpus corpus.jsonl --seed 1 --out artifacts/

# 4. Weight-only int8 export. Gate: >= 0.98 mean cosine to the fp32 student.
awembed quantize --corpus corpus.jsonl --seed 1 --out artifacts/

# 5. Teacher vs untrained baseline vs student vs int8 on the held-out directories.
awembed eval     --corpus corpus.jsonl --seed 1 --out artifacts/

# All four artifact stages, stopping at the first gate that refuses:
awembed run      --corpus corpus.jsonl --seed 1 --out artifacts/
```

## Things that cost a run each, so you do not have to pay for them

- **Probe first.** The teacher's remote code needs `einops`, `datasets` and
  `accelerate`; without them it dies at load, after you have paid for the machine.
- **The teacher's backbone loads fp32 whatever dtype you ask for** — 27.9 GB for a
  14.6 GB checkpoint. The teacher module casts explicitly; if you serve it another way,
  cast after load or a 24 GB card will OOM in fp16 *and* bf16.
- **Two environments.** The default teacher pins an older `transformers` than the
  student needs (its cache API broke on the first forward under 4.55+). Run
  `teacher`/`probe` in their own venv and point `capture` at it:
  `NV_EMBED_PYTHON=/path/to/venv/bin/python awembed capture ...`
- **Activations, not weights, are what OOM the trainer** — batch 16 with 3 negatives is
  80 sequences per step with grad. Gradient checkpointing is on by default on CUDA.
- **Dynamic int8 wrecks Qwen3-family MLPs** (cosine 0.87). The quantize stage uses
  weight-only per-channel int8 (0.999) for that reason; do not "optimise" it back.

## Using what you trained

`artifacts/student/` is an ordinary Hugging Face directory. Serve it with vLLM
(`--task embed`), Text Embeddings Inference, or `transformers` directly. Two rules:

1. **Queries carry the instruction prefix the student was trained with; documents do
   not.** The prefix is in `train_sidecar.json`. Omit it on queries and the vector
   spaces stop matching.
2. **It is a new vector space.** Index into a fresh collection. A 1024-dim vector into a
   768-dim collection is a write error; a mixed collection scores garbage silently.

Then point the family at it: `awgraph` (set its code-embed URL, model and query
prefix), `awm` (agent memory), `awfind` (ranked answers), `awrecurse` (documents beyond
a context window), and any `awdk` agent that uses those tools.

## Licences

Your student carries its base model's licence (the default student,
Qwen3-Embedding-0.6B, is Apache-2.0). The default teacher, NV-Embed-v2, is
CC-BY-NC-4.0: use it as a signal, keep its weights and its captured targets out of
anything you ship. The sidecars record which teacher revision supervised the run.
