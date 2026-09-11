# A platform you cannot ship to is not supported — the OmniOS law
*Part IV · Deployment*

**Fires when:** you say a thing "runs on" Windows, macOS, Linux, WSL, a VM, a
container or an ISO — and when you add a platform to a README, a release page,
or a roadmap.

## The law

Support is **per-platform and per-lane**. One artifact that happens to be
portable is not support; a lane that carries it to that platform, and that can
FAIL, is.

Three questions, per platform, and all three have to have answers:

1. **What is the artifact?** A wheel, a `.deb`, an ISO, an image, a formula.
2. **What lane carries it there, and can that lane fail?** If nothing exits
   non-zero when the lane breaks, the platform is unsupported and nobody will
   find out.
3. **Who ran it there?** Not "it should work" — code being portable is a
   prediction, not a measurement.

Answer 1 and 2 and skip 3 and you have a claim. Answer 3 for one platform and
list five and you have advertised four you have not shipped.

**The OmniOS protocol** is the operational form: one product, a declared lane
per platform, each lane independently provable, each failure visible. A
platform without a lane is not "coming soon" — it is a platform you do not
support, and saying so plainly is worth more than a roadmap line.

## The measurement that produced this

Measured 2026-08-23 across one product family:

| platform | artifact | lane | proven |
|---|---|---|---|
| Linux container | image | build + assert | **yes** — UI serves, model answers offline |
| Linux ISO / VM | ISO parts | CI workflow | build lane green; **never dispatched for this variant** |
| WSL2 | rootfs tarball | `awnix-to-wsl.sh` | **yes** — imported, models and CLI present |
| Windows | wheel via pip | PyPI | **yes** — CI matrix |
| macOS | wheel via pip | PyPI | **yes** — CI matrix on a real Mac runner |
| macOS | `brew install` | tap | **404 — the tap has no formula** |

The brew row is the law in miniature. A formula existed in-repo, a tap existed,
a publish step existed — and the step began:

    git clone https://.../homebrew-tap.git tap || exit 0

A failed clone exits **successfully**, the next line copies into a directory
that is not there, and the release goes green having published nothing. The
step was additionally `continue-on-error: true` and gated on a repository
condition that is false where it lives. Three independent silences in one step,
and the only thing that could ever have surfaced them was fetching the URL:
`Formula/awdk.rb` → **404**.

Meanwhile the same product's macOS support was real in every way that did not
involve a lane: the wheel is `py3-none-any`, the launcher has zero platform
branches, and the installer already detects `macos` / `arm64` / Metal and picks
a `macos-arm64` asset. Everything was ready except the thing that delivers it.

The inverse case, from the same day: a neighbouring project shipped Linux as a
`.deb` built from a Go port, as a **release asset**, while its default branch
stayed PowerShell-only. That is a lane — a real, verifiable one — and it made
Linux supported the moment it existed, regardless of what the source tree
looked like.

## The cheapest lane is usually the one nobody checked for

The macOS row above said "inferred, never run on a Mac" for exactly as long as
it took someone to ask why not. The plan at that moment was an AWS EC2 Mac: real
hardware, and priced accordingly — Mac instances are **Dedicated Hosts with a
24-hour minimum allocation**, so the floor is 24h x the hourly rate however
short the test is, roughly $16–26. Measured the same day, this account's quota
for every Mac host type is **0**, so the first step would not even have been a
launch — it would have been a quota request with days of lead time.

The actual answer cost nothing. **GitHub gives public repositories free hosted
runners, macOS included.** The billing-dead problem on this org is confined to
PRIVATE repos; the public mirror's `ubuntu-latest` CI had been going green all
along, which was the proof sitting in plain sight. A three-OS matrix on the
public repo now proves the lane on **every push**, instead of once, for money.

So: before pricing a lane, check whether the platform is already reachable from
somewhere you publish. The expensive answer is easy to find because it is the
one that feels proportionate to the difficulty.

And run it. That first matrix failed on all three OSes at once, because it
asserted `adk --version` — a flag the CLI does not have. The same false
assertion was sitting in the Homebrew formula's `test do`, published an hour
earlier, where `brew test` would have failed for the same reason. A comment
directly above it warned against asserting a command the package does not
ship.

## What to do instead

Write the lane table down, per platform, and make each row carry the command
that fails. Then treat an empty "proven" cell as an unsupported platform in
public, not as a nearly-finished one.

Asserted by `SHW024` (a delivery command ending in `|| exit 0` cannot report
its own failure), `SHW021` (an irreversible publish masked by
`continue-on-error`), and `ONB003` (an advertised install target that 404s on
its registry).

## See also

- [Detection without delivery is not detection](09-detection-without-delivery-is-not-detection.md)
- [Written is not deployed](13-written-is-not-deployed.md)
- [You wrote it — that does not mean it ships](14-you-wrote-it-that-does-not-mean-it-ships.md)
- [A check that cannot run must not pass](06-a-check-that-cannot-run-must-not-pass.md)
