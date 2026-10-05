"""Allocate the next free debt-ledger id — atomically, so it cannot collide.

    python tools/next_debt_id.py          # -> the next free id, reserved
    python tools/next_debt_id.py --audit  # report duplicate ids
    python tools/next_debt_id.py --release <id>    # give one back
    python tools/next_debt_id.py --self-test       # prove --release is confined

WHY THIS IS NOT JUST max()+1
----------------------------
It used to be. It scanned the whole ledger, printed max+1, and RESERVED NOTHING
— so two sessions that ran it minutes apart both got the same number and both
appended. Its docstring claimed it "kills concurrent-session id collisions"; an
audit on 2026-07-25 found **166 ids used more than once across 370 rows**, the
worst of them used five times. Scanning harder cannot fix a race: the read was never the
problem, the missing write was.

Allocation now takes an exclusive reservation file per id (`O_CREAT|O_EXCL`,
atomic on Windows and POSIX alike) and walks forward until it wins one. A
crashed session leaks a reservation, which costs one integer — far cheaper than
two rows sharing an id, because `[[D-xxx]]` cross-references then point at two
different things.

Reservations live in a gitignored directory: every concurrent session here runs
on the same host, so a local file IS the mutex. They are swept automatically
once the id shows up in the ledger.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# Ledger filename, overridable so this works in any repo.
LEDGER_NAME = os.environ.get("DEBT_LEDGER", "TECH_DEBT.md")

RESERVATION_DIR = ".tech-debt-ids"
_ID_RE = re.compile(r"\bD-(\d{1,5})\b")


def _ledger_ids(text: str) -> set[int]:
    """Every id the ledger mentions anywhere.

    Deliberately not just row starts: renumber notes ("RENUMBERED from <id>")
    and `[[D-xxx]]` cross-references also permanently reserve an id, because
    reusing one silently repoints an existing reference.
    """
    return {int(m) for m in _ID_RE.findall(text)}


def _reserved_ids(res_dir: Path) -> set[int]:
    if not res_dir.is_dir():
        return set()
    out: set[int] = set()
    for p in res_dir.iterdir():
        m = re.fullmatch(r"D-(\d{1,5})", p.name)
        if m:
            out.add(int(m.group(1)))
    return out


REMOTE_REFS = ("@{upstream}", "origin/HEAD", "origin/develop")


def _repo_root() -> Path:
    """Locate the repo root WITHOUT assuming how deep this file is nested.

    Resolving by level count (`parents[3]`) is how the same tool broke when it was
    copied to a directory one level shallower: it walked past the repo and landed on
    the drive root, then reported the ledger 'not found'. Ask git; fall back to
    walking up for the ledger or a .git dir; fall back to cwd.
    """
    here = Path(__file__).resolve().parent
    try:
        out = subprocess.run(
            ["git", "-C", str(here), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace",
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError) as exc:
        # Fall through to the walk — but SAY SO. A silent handler here turns
        # "git is not on PATH" into "the ledger is somewhere else", and the
        # walk then picks a plausible wrong root without anyone noticing.
        print(f"note: git rev-parse failed ({exc}); falling back to a "
              f"parent walk for the ledger root", file=sys.stderr)
    for parent in [here, *here.parents]:
        if (parent / LEDGER_NAME).is_file() or (parent / ".git").exists():
            return parent
    return Path.cwd()


def _remote_ids(repo_root: Path, refs: tuple[str, ...] = REMOTE_REFS) -> set[int]:
    """Ids already pushed, which the LOCAL ledger may not have yet.

    The reservation file only serialises processes sharing this checkout. It
    does nothing about the other half of the race: a session that already
    PUSHED a row while this checkout is behind origin. That is not theoretical
    — the first id this tool allocated after being fixed collided with
    a row another session had already pushed, because the local file was stale.

    Best-effort by design: no fetch (too slow and side-effecting for an id
    lookup), and any git failure returns empty so allocation still works
    offline or outside a repo. Union it with the local ids, never trust it
    alone.
    """
    import subprocess

    ids: set[int] = set()
    for ref in refs:
        try:
            out = subprocess.run(
                ["git", "-C", str(repo_root), "show", f"{ref}:{LEDGER_NAME}"],
                capture_output=True, timeout=20, check=False,
                # NOT text=True: that decodes with the LOCALE codec (cp1252 on
                # Windows), which raises UnicodeDecodeError inside subprocess's
                # reader thread on this UTF-8 ledger. The exception never
                # reaches the caller, so the lookup silently returned nothing
                # and this whole guard degraded to a no-op that looked fine.
                encoding="utf-8", errors="replace",
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if out.returncode == 0 and out.stdout:
            ids |= _ledger_ids(out.stdout)
            break
    return ids


def next_debt_id(ledger_path: Path) -> str:
    """Back-compat: the pure max()+1 answer, WITHOUT reserving it.

    Kept because callers imported it. Do not use it to allocate — it is exactly
    the racy behaviour that produced 166 duplicate ids. Use allocate().
    """
    ids = _ledger_ids(ledger_path.read_text(encoding="utf-8", errors="replace"))
    return f"D-{(max(ids) + 1) if ids else 1}"


def allocate(
    ledger: Path, res_dir: Path, *, start: int | None = None, check_remote: bool = True
) -> str:
    """Reserve and return the next free id. Atomic against concurrent callers.

    Three id sources are unioned, because each covers a different half of the
    race: the local ledger (committed rows), the reservation dir (other
    processes in this checkout), and the pushed ledger (sessions that committed
    while this checkout is behind). Missing the third is how the very first id
    this tool allocated still collided.
    """
    res_dir.mkdir(parents=True, exist_ok=True)
    used = _ledger_ids(ledger.read_text(encoding="utf-8", errors="replace"))
    used |= _reserved_ids(res_dir)
    if check_remote:
        try:
            used |= _remote_ids(ledger.parent)
        except Exception as exc:  # noqa: BLE001 - an id lookup must never fail hard
            # Losing the remote view risks a collision; failing to allocate at
            # all blocks every session. Degrade, do not stop — but VISIBLY:
            # the whole reason for the remote view is that a local-only read
            # already handed out a colliding id once, and a silent degrade
            # returns to exactly that state while looking identical.
            print(f"warning: could not read remote ids ({exc}); allocating from "
                  f"the LOCAL view only — a concurrently pushed row could collide",
                  file=sys.stderr)
    candidate = start if start is not None else (max(used) + 1 if used else 1)
    while True:
        if candidate in used:
            candidate += 1
            continue
        try:
            # O_EXCL is the whole point: the winner is decided by the OS, not by
            # who read the ledger most recently.
            fd = os.open(
                res_dir / f"D-{candidate}", os.O_CREAT | os.O_EXCL | os.O_WRONLY
            )
        except FileExistsError:
            candidate += 1
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(f"reserved by pid {os.getpid()}\n")
        return f"D-{candidate}"


def sweep(ledger: Path, res_dir: Path) -> int:
    """Drop reservations whose id is now present in the ledger."""
    if not res_dir.is_dir():
        return 0
    used = _ledger_ids(ledger.read_text(encoding="utf-8", errors="replace"))
    dropped = 0
    for p in sorted(res_dir.iterdir()):
        m = re.fullmatch(r"D-(\d{1,5})", p.name)
        if m and int(m.group(1)) in used:
            p.unlink()
            dropped += 1
    return dropped


_RELEASE_RE = re.compile(r"D-\d{1,5}")


def release(res_dir: Path, ident: str) -> tuple[int, str]:
    """Delete ONE reservation file. Returns (exit_code, message).

    `ident` comes from the command line, so it is validated as an id
    (`D-<digits>`) and the resolved target must sit directly inside the
    reservation dir: `--release ../TECH_DEBT.md` once unlinked the ledger.
    """
    if not _RELEASE_RE.fullmatch(ident or ""):
        return 2, f"refusing --release {ident!r}: expected an id like D-<n>"
    base = res_dir.resolve()
    target = (res_dir / ident).resolve()
    if target.parent != base:
        return 2, f"refusing --release {ident!r}: resolves outside {base}"
    if target.is_file():
        target.unlink()
        return 0, f"released {ident}"
    return 1, f"no reservation for {ident}"


def _self_test() -> int:
    """Fails on the old behaviour (an unchecked --release path)."""
    import tempfile

    fails: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / LEDGER_NAME
        ledger.write_text("| D-1 | row |\n", encoding="utf-8")
        res = root / RESERVATION_DIR
        res.mkdir()
        (res / "D-7").write_text("x", encoding="utf-8")
        for bad in (f"../{LEDGER_NAME}", str(ledger), "D-7/../../" + LEDGER_NAME, "x"):
            code, _ = release(res, bad)
            if code == 0 or not ledger.is_file():
                fails.append(f"--release {bad!r} was accepted or removed the ledger")
                ledger.write_text("| D-1 | row |\n", encoding="utf-8")
        code, _ = release(res, "D-7")
        if code != 0 or (res / "D-7").exists():
            fails.append("--release D-7 did not remove a valid reservation")
        if release(res, "D-8")[0] != 1:
            fails.append("--release of a missing id did not exit 1")
    for f in fails:
        print(f"SELFTEST FAIL: {f}", file=sys.stderr)
    if not fails:
        print("SELFTEST PASS: --release accepts only D-<n> inside the reservation dir")
    return 1 if fails else 0


def audit(ledger: Path) -> tuple[int, list[tuple[str, int]]]:
    """Duplicate ROW ids in the ledger. Returns (row_count, [(id, times)])."""
    counts: dict[str, int] = {}
    rows = 0
    for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("| D-"):
            rows += 1
            did = line.split("|")[1].strip()
            counts[did] = counts.get(did, 0) + 1
    dups = sorted(((k, v) for k, v in counts.items() if v > 1), key=lambda x: -x[1])
    return rows, dups


def main() -> int:
    ap = argparse.ArgumentParser(description="Allocate/audit TECH_DEBT.md ids")
    ap.add_argument("--audit", action="store_true",
                    help="report duplicate ids; exit non-zero if any exist")
    ap.add_argument("--release", metavar="D-NNN",
                    help="release a reservation that was taken but not used")
    ap.add_argument("--sweep", action="store_true",
                    help="drop reservations whose id is already in the ledger")
    ap.add_argument("--self-test", action="store_true",
                    help="run the built-in regression test and exit")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    root = _repo_root()
    ledger = root / LEDGER_NAME
    res_dir = root / RESERVATION_DIR
    if not ledger.is_file():
        print(
            f"{LEDGER_NAME} not found at {ledger}.\n"
            f"Run from inside the repo, or set DEBT_LEDGER to the ledger filename.",
            file=sys.stderr,
        )
        return 1

    if args.audit:
        rows, dups = audit(ledger)
        affected = sum(v for _, v in dups)
        print(f"{rows} rows; {len(dups)} duplicated ids across {affected} rows")
        for did, n in dups[:20]:
            print(f"  {did} used {n}x")
        return 1 if dups else 0

    if args.release:
        code, msg = release(res_dir, args.release)
        print(msg, file=sys.stdout if code == 0 else sys.stderr)
        return code

    if args.sweep:
        print(f"swept {sweep(ledger, res_dir)} reservation(s)")
        return 0

    sweep(ledger, res_dir)
    print(allocate(ledger, res_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
