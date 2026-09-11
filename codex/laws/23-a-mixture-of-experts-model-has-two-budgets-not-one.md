# A mixture-of-experts model has two budgets, not one — the resource coupling law
*Part VII · Scaling*

**Fires when:** sizing, optimizing, or deploying a mixture-of-experts (MoE) model,
or any system where routed components live in separate memory tiers.

## The law

For a dense model, "VRAM needed" and "bandwidth per token" are almost the same number. A
model that fits in GPU memory consumes that many bytes per token. Double both
numbers or halve both numbers together.

**For an MoE model, they are decoupled by a factor of 10–100x.** A model that
barely fits in GPU memory may have a per-token bandwidth measured in megabytes.
A model may have enormous per-token bandwidth while its resident weights fit in
a quarter of the card.

**Sizing one of them by the other inverts your optimization.**

## The numbers that proved this

Measured 2026-08-16 on a production Mixture-of-Experts model (K3, top-16-of-896,
2.78 trillion parameters):

- **Resident footprint:** 1,600 GB (active trunk + routed expert subsets)
- **Bandwidth per token:** 135 GB/token

**These are 12x apart.** A tactic that makes sense for "how do I fit this in
VRAM" is exactly the wrong tactic for "how do I get throughput".

## Why they decouple

In a dense model every token reads every weight. Both constraints are
proportional to model size.

In an MoE model:
- **Resident capacity** depends on what you keep in memory: the full trunk, the
  full expert set, a routed subset, or a mix.
- **Per-token bandwidth** depends on what is *routed* for *each* token. A model
  with 1,000 experts and top-2 routing reads 2 experts per token, regardless of
  whether the other 998 are in VRAM or on a slow NVMe or not present at all.

So a model can have small per-token bandwidth with enormous resident capacity, or
enormous per-token bandwidth with a small resident capacity, or any combination.

## The trap that inverts the ranking

You decide to optimize for speed. You measure per-token bandwidth and conclude
"experts are the problem". You optimize by reducing expert memory: quantize them,
place them on slower storage, or evict them.

But a dense model tells you the inverse relationship is tight: save bytes on
experts, save tokens per second. So you ship the fix.

**On an MoE, quantizing the experts by 50% cuts per-token bandwidth by 50%. But
quantizing the trunk by 50% cuts per-token bandwidth by only 15%** (if the trunk
is 85% of the per-token read and the experts are 15%, which is the actual
distribution in the K3 case).

Sizing by resident bytes ranked them the wrong way. The fix is now in place, and
your throughput got worse.

## The operational form

When sizing an MoE system, measure and state **both**:

1. **Resident capacity:** "This model requires X GB to fit (resident trunk,
   experts Y–Z routed for each token, miscellaneous overhead)."
2. **Per-token bandwidth:** "Each token moves Y GB across the interconnect (trunk
   reads + expert reads + miscellaneous overhead)."

**Never use one to derive the other.** They are independent constraints.

When choosing an optimization tactic, ask which constraint you are trying to
improve:
- **To make it fit:** optimize resident capacity. Quantization helps if it keeps
  quality stable. Batching helps if it amortizes the overhead.
- **To make it faster:** optimize per-token bandwidth. This is throughput, not
  capacity. Which layers read the most bytes per token? Optimize those.

If the ranking of tactics differs between your two measurements, that is the
sign that you are sizing by the wrong number.

## The tiering pattern that follows from this

Because the two budgets are decoupled, you can tier them:

- **Tier 1 (fastest):** Resident in on-chip memory or PCIe-attached VRAM. Full
  bandwidth available to the token.
- **Tier 2 (medium):** Resident in host memory (DRAM far from the GPU). Bandwidth
  bottleneck. Prefetch strategically to hide the cost.
- **Tier 3 (slowest):** On disk or network (NVMe, cloud storage). Extreme
  bandwidth bottleneck. Page only what is needed. Measure before assuming paging
  is feasible — a 1 GB expert read from cloud storage at 1 MB/s is 1,000 seconds
  per expert.

**A split architecture where the trunk lives in GPU VRAM and hottest experts live
in local NVMe is viable on local hardware. A split where experts spill to cloud
storage is usually not** — measure the bandwidth on your actual infrastructure
before committing to it.

## When this matters most

This law is critical for:
- **Specifying hardware for an MoE model** — asking the wrong question
  ("how much GPU memory do I need?") leads you to the wrong number (GPU memory
  needed for other layers).
- **Choosing quantization strategies** — optimizing for model size helps
  capacity, not speed.
- **Judging paging feasibility** — whether you can run the model with some
  components off-device depends on per-token bandwidth, not resident size.
- **Distributing experts across a cluster** — the optimal distribution depends
  on network bandwidth relative to per-token reads, not on how many experts
  you have or how big each one is.
