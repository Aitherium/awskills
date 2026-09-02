#!/usr/bin/env python3
"""Assert the checker contract against the checkers themselves.

WHY THIS EXISTS (2026-08-08)
---------------------------------------------------------------------------
The coding discipline this repo follows (its debt-ledger rule) says a
mechanically-detectable defect must become a CHECK, not a ledger row, and that
every check must:

  1. have a ``--self-test`` that proves it can still fail,
  2. be wired somewhere unattended (CI or a routine),
  3. exit non-zero (2), never 0, when it cannot run,
  4. name a debt id in any allowlist entry, printed on every run.

Nothing asserted that the checkers obey their own contract. Docs drifted from
reality (the ledger rule said "22 checkers"; the gate tree holds ~140).
This check is the process codified: it reads the rules, the CI workflow and the
routine gate list and asserts the contract against the tools they name.

Invariants
---------------------------------------------------------------------------
  HYG001 (gate)   every checker that is DOCUMENTED (named in the quality-gate
                  rules) or WIRED (named in the debt-invariants workflow or the
                  debt-gate-probe routine) declares a ``--self-test``. A gate
                  that cannot prove it can fail is not a gate.
  HYG002 (gate)   every checker path named in the quality-gate rules exists on
                  disk. A documented gate that is not a file is a broken ref.
  HYG003 (gate)   every checker wired in CI or a routine exists on disk. A
                  wired gate that is not a file runs nothing.
  HYG004 (report) the backlog a gate must never open with: wired-but-
                  undocumented checkers (an invisible gate nobody can
                  question), total ``check_*.py``, how many lack ``--self-test``
                  tree-wide, and how many are wired nowhere. Printed by
                  ``--all``; never a gate. A check that floods gets switched
                  off, which is how this repo's per-file-ignores came to exist.
  HYG005 (gate)   the discipline's duplicated artifacts stay IDENTICAL across
                  their delivery homes — the portable twin in awskills,
                  the bundled awdk pack, and the published pack template.
                  A drift between copies is the "duplicated source of truth"
                  hazard awknowledge rule 11 calls active: editing one
                  copy silently orphans the others. Skipped for a layout that
                  does not carry a given home.

A probe that cannot read its sources exits 2, never 0 — silence is not a pass.
Use ``--self-test`` to prove it can still fail (it points the reference set at
a nonexistent file and asserts the gate goes red).

Portable twin lives at ``awskills/tools/check_checker_hygiene.py`` — same
logic, layout-detected root (AitherOS monorepo, generic ``dev/tools`` install,
or bare ``tools/``), so an external repo that adopted the discipline can run it.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Gate tools that are NOT named check_*.py but ARE gates. Used so a bare
# mention in the rules or a run line is still recognised as a gate.
NON_CHECK_GATES = {
    "probe_service_schemes.py",
    "security_lint.py",
    "rotate_internal_secret.py",
    "repair_ps1_encoding.py",
    "check_actions_allowlist.py",
    "debt_ledger.py",
    "triage_debt_ledger.py",
    "next_debt_id.py",
}

# Any `<something>.py` token in the rules/run text.
TOKEN_RE = re.compile(r"([A-Za-z_][\w.-]*\.py)\b")
# `python <path>/<name>.py` on a workflow run line (path may be relative or
# absolute, possibly with subdirs like dev/tools/pool/).
WF_RUN_RE = re.compile(r"\b(?:python|python3)\s+([\w./-]+\.py)")
# A quoted tool name inside the debt-gate-probe routine or a routine yaml.
ROUTINE_STR_RE = re.compile(
    r'"((?:check_|compare_|security_lint|rotate_internal|repair_ps1)[\w-]*\.py)'
)

# ── Repo layout: the ONLY monorepo-specific data, and it does not live here ──
#
# This module is a PORTABLE TWIN: byte-identical copies ship in awskills and
# the awdk code-discipline pack, and the parity rule below asserts that
# identity. Those two facts used to be in direct conflict with a third — the
# published-tree path scan
# forbids monorepo-internal paths in anything that ships, and this file hardcoded
# nine of them (the PARITY registry, the checker-root candidates, the host-gate
# runner, the debt probe, the self-test fixtures).
#
# The result was a twin that could be neither excluded from publishing
# (SYNC_EXCLUDES is skills-only) nor deleted (PARITY requires the home), so the
# skills mirror simply stopped publishing on 2026-08-13 and stayed stopped.
#
# Resolution: the paths are DATA, in an optional file beside this one. The
# monorepo ships it; a public reader does not have it and gets portable defaults.
# Both copies stay byte-identical AND carry no path a stranger cannot follow.
#
# A rule whose data is absent reports NOT APPLICABLE — never silently passes.
# "No parity registry" and "parity holds" are different facts, and collapsing
# them would make this gate vacuous in exactly the home it ships to.
LAYOUT_FILE = Path(__file__).resolve().parent / "checker_hygiene_layout.json"

#: Where the self-test puts its synthetic rules document. Deliberately a
#: neutral path: this module ships publicly, and the fixture must not name
#: any real repo's private layout.
_SELFTEST_RULES_REL = "docs/gate-rules.md"

_PORTABLE_DEFAULTS: dict = {
    "checker_roots": ["dev/tools", "tools"],
    "parity": [],
    "host_gate_runner": None,
    "routines_dir": None,
    "debt_probe": None,
    # HYG010's subject. Hardcoding the app's monorepo path here would put a
    # monorepo-internal path into a file that ships to a public pack (the exact conflict
    # the layout indirection above exists to resolve), and would make the portable twin
    # unable to stay byte-identical. Absent => HYG010 reports NOT APPLICABLE.
    "jest_app": None,
    # HYG001/2/3's subject. Same reasoning as jest_app: the rules document lives at a
    # repo-specific path, so hardcoding it here would put an internal path into a file
    # that ships to a public pack. Absent => those rules report NOT APPLICABLE.
    "rules_doc": None,
}


def _load_layout() -> dict:
    """Repo layout from the sibling data file, else portable defaults."""
    layout = dict(_PORTABLE_DEFAULTS)
    try:
        if LAYOUT_FILE.is_file():
            data = json.loads(LAYOUT_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                layout.update({k: v for k, v in data.items() if k in layout})
    except (OSError, ValueError) as exc:
        # A malformed layout must be LOUD. Falling back to defaults would silently
        # downgrade every monorepo-only rule to "not applicable" and report green.
        raise SystemExit(f"DEAD: {LAYOUT_FILE} is unreadable/malformed: {exc}")
    return layout


LAYOUT = _load_layout()

#: Artifacts intentionally duplicated across delivery homes. The parity rule asserts each
#: copy stays byte-identical to its canonical, so editing one home cannot silently
#: orphan the others. Empty outside the monorepo — see LAYOUT_FILE above.
PARITY = [tuple(p) for p in LAYOUT["parity"] if isinstance(p, (list, tuple)) and len(p) == 2]


#: Copies that CANNOT be byte-identical to canonical, with the reason. Two gates are
#: in genuine tension here and silently breaking either one is worse than recording
#: the decision: HYG005 wants identical copies, while ADK001 forbids internal
#: identifiers in the tree that publishes to PyPI — and this checker's own rule ids
#: (HYG001-009) and the debt ids in its comments ARE those identifiers. Syncing it
#: verbatim measurably raised ADK001 from 124 to 128 on 2026-08-16.
#: Printed on every run; may only ratchet DOWN. The durable fix is to stop shipping
#: an internal discipline tool in a public pack, which is an owner decision.
_HYG005_BOUNDARY_EXEMPT: dict[str, str] = {
    # Path updated aither-adk -> awdk on 2026-08-21. The rename moved the tree
    # and left this key naming a path that no longer exists, so the exemption
    # matched NOTHING and HYG005 fired on an exemption that was already granted.
    "awdk/adk/packs/code-discipline/tools/check_checker_hygiene.py":
        "ships to PyPI; canonical carries HYG00x rule ids + debt ids that ADK001 bans",
}


def _parity_normalise(raw: bytes) -> bytes:
    """Content as the parity rule should judge it.

    Line endings, because git hands one copy CRLF and the other LF depending on
    .gitattributes -- a byte-exact compare measures the CHECKOUT, not the content.

    And the `name:` FRONTMATTER KEY, because the two delivery homes disagree about
    it by design: every skill under awskills carries `name:`, and every skill in the
    adk pack omits it. Measured 2026-08-22, that one line was the ENTIRE difference
    between both flagged pairs -- 2 diff lines each, on files of ~139 lines.

    Exempting the pair was the obvious move and is the wrong one: an exemption would
    hide any future drift in the skill BODY, which is the only thing this rule exists
    to protect. Normalising the key that differs on purpose keeps the rule live for
    everything that does not.
    """
    out = raw.replace(b"\r\n", b"\n")
    return b"\n".join(ln for ln in out.split(b"\n") if not ln.startswith(b"name:"))


def _hyg5(root: Path) -> list[str]:
    """Copy-parity violations across the discipline's delivery homes.

    A pair is asserted only when THIS layout carries both the canonical and the
    copy's home: a generic adopted repo has neither awskills nor the adk
    pack, so skipping there is correct, not a pass-by-omission.
    """
    violations: list[str] = []
    for canon_rel, copy_rel in PARITY:
        if copy_rel in _HYG005_BOUNDARY_EXEMPT:
            continue
        canon = root / canon_rel
        copy = root / copy_rel
        if not canon.is_file():
            continue
        if not copy.parent.exists():
            continue
        if not copy.is_file():
            violations.append(f"{copy_rel} missing (canonical {canon_rel} exists)")
            continue
        # Compare with line endings NORMALISED. A byte-exact compare measures the
        # CHECKOUT, not the content: git hands one copy CRLF and the other LF depending
        # on .gitattributes, so on a Windows working tree every line of both skill files
        # "differed" — 278 and 276 changed lines across files of 139 and 138 lines,
        # i.e. twice the file, which is the signature of a pure newline difference and
        # nothing else. Measured 2026-08-17: both are IDENTICAL after normalisation.
        #
        # That made HYG005 permanently red here for a difference no author can fix by
        # editing either file, and a gate that opens red gets bypassed rather than
        # satisfied — how this repo's per-file-ignores came to exist.
        #
        # Same decision, same reasoning, already taken once in this repo: gate 1zj's
        # TP018 normalises newlines for exactly this, having found byte-exact compare
        # called 69 files stale where 10 were real.
        if _parity_normalise(canon.read_bytes()) != _parity_normalise(copy.read_bytes()):
            violations.append(f"{copy_rel} differs from canonical {canon_rel}")
    return violations


def _safe_print(text: str) -> None:
    """Never let the console codec stop a verdict (Windows cp1252 + a
    non-ASCII finding would otherwise raise UnicodeEncodeError mid-report,
    truncating the list — the exact class check_skills_publishable.py guards)."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(enc, "replace").decode(enc, "replace"))


def find_root(start: Path) -> Path:
    """Repo root via git; fall back to walking up for a marker."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError) as exc:
        # git missing / not a repo / too slow — fall through to the marker
        # walk. Not silent: a root we could not resolve from git is diagnostic
        # noise, never a verdict (the sources themselves gate on exit 2).
        print(f"[check_checker_hygiene] git rev-parse unavailable ({exc}); "
              f"walking up for a marker", file=sys.stderr)
    cur = start.resolve()
    for p in (cur, *cur.parents):
        if (p / ".git").exists() or (p / ".claude").exists():
            return p
    return cur


def candidate_trees(root: Path) -> list[Path]:
    """Every plausible checker tree, in priority order, from LAYOUT.

    Resolution spans ALL of them because a checker can live at repo-root
    `dev/tools` rather than under the primary tree. The list is data (see
    LAYOUT_FILE) so this module names no repo's private layout.
    """
    out: list[Path] = []
    for rel in LAYOUT["checker_roots"]:
        cand = root / rel
        if cand.is_dir():
            out.append(cand)
    return out


def detect_gate_tree(root: Path) -> Path | None:
    """The primary checker tree (first that exists)."""
    trees = candidate_trees(root)
    return trees[0] if trees else None


def _is_gate(name: str) -> bool:
    return name.startswith("check_") or name in NON_CHECK_GATES


def documented_gates(rules: Path) -> set[str]:
    """Basenames named in the quality-gate rules file."""
    text = rules.read_text(encoding="utf-8", errors="replace")
    names = set()
    for m in TOKEN_RE.finditer(text):
        name = m.group(1)
        if _is_gate(name):
            names.add(name)
    return names


def wired_in_workflow(workflow: Path) -> set[str]:
    """Basenames of checkers invoked on a workflow run line."""
    text = workflow.read_text(encoding="utf-8", errors="replace")
    names = set()
    for m in WF_RUN_RE.finditer(text):
        base = Path(m.group(1)).name
        if _is_gate(base):
            names.add(base)
    return names


def wired_in_host_gates(root: Path) -> set[str]:
    """Checkers wired into the HOST-ONLY gate runner (every 4h from Windows).

    🚨 THE THIRD WIRING HOME, and the missing-on-disk rule was blind to it.
    That rule promises "every checker wired in CI or a routine exists on disk",
    and it read exactly two sources: the CI workflow and the routines directory.
    But a whole class of gates can run in NEITHER — anything needing the host's
    task scheduler, the WSL distro's units, or a key that exists only on the
    fleet box — and those are registered in `HOST_ONLY_GATES` in the host gate
    runner. Eighty-one gates, none of them examined.

    Found 2026-08-15 while registering a new gate there: one entry in that list
    names a checker that **does not exist anywhere in the tree**. It has been
    running nothing, every four hours, silently — which is the exact defect the
    rule exists to catch, in the one place the rule could not look.

    The general lesson, which is why this matters beyond one entry: **a gate that
    guards other gates must enumerate every place a gate can be wired.** A wiring
    home it cannot read is not a smaller check, it is a blind spot that reports
    healthy.

    Entries may be a bare filename or a (filename, *args) tuple, so the name is
    taken from the runner's own `_gate_names()` shape rather than re-parsed.
    """
    rel = LAYOUT["host_gate_runner"]
    if not rel:
        return set()  # not applicable outside a repo that declares a host runner
    runner = root / rel
    if not runner.is_file():
        return set()
    text = runner.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^HOST_ONLY_GATES\s*=\s*\[(.*?)^\]", text, re.S | re.M)
    if not m:
        return set()
    # Match "check_*.py" whether bare or the first element of a tuple. Comments
    # are stripped first: this file documents past defects in prose, and the
    # checker names inside those comments are references, not wirings.
    body = "\n".join(ln for ln in m.group(1).splitlines()
                     if not ln.lstrip().startswith("#"))
    return set(re.findall(r"[\"'](check_[A-Za-z0-9_]+\.py)[\"']", body))


def wired_in_routines(routines_dir: Path | None, probe: Path | None) -> set[str]:
    """Basenames of checkers named in the gate routine or any routine yaml.

    Either source may be None when LAYOUT does not declare it (a repo with no
    routines plane). That is NOT APPLICABLE, not "nothing is wired" — the caller
    reports the distinction; here it simply contributes no names.
    """
    names: set[str] = set()
    for source in (probe,):
        if source is not None and source.is_file():
            text = source.read_text(encoding="utf-8", errors="replace")
            for m in ROUTINE_STR_RE.finditer(text):
                names.add(Path(m.group(1)).name)
    if routines_dir is not None and routines_dir.is_dir():
        for yml in sorted(routines_dir.glob("*.yaml")):
            text = yml.read_text(encoding="utf-8", errors="replace")
            for m in ROUTINE_STR_RE.finditer(text):
                names.add(Path(m.group(1)).name)
    return names


def resolve(name: str, trees: list[Path]) -> Path | None:
    """A file under any gate tree matching the basename (top-level or nested)."""
    for tree in trees:
        direct = tree / name
        if direct.is_file():
            return direct
        for hit in tree.rglob(name):
            if hit.is_file():
                return hit
    return None



# Handlers that mean "I could not read this input".
# Deliberately narrow: only the "I could not ANALYSE this source" family. The first
# version also listed OSError/ValueError/FileNotFoundError and produced a flood (100+
# hits) — because a helper returning a default for a missing OPTIONAL file is correct,
# not a defect. A rule that floods gets switched off, which is how this repo's
# per-file-ignores came to exist, so the rule is scoped to the shape that actually
# caused all three measured incidents: a PARSE failure reported as no findings.
_CANNOT_READ_EXC = {
    "SyntaxError", "UnicodeDecodeError", "IndentationError", "TokenError",
}
# Return values that mean "nothing to report" — i.e. CLEAN.
def _is_clean_return(node: "ast.AST") -> bool:
    """True if this return says 'no findings' rather than 'I could not judge'."""
    v = getattr(node, "value", None)
    if v is None:
        return True                                   # bare `return`
    if isinstance(v, ast.Constant) and v.value in (None, 0, True):
        return True
    if (isinstance(v, (ast.List, ast.Dict, ast.Set))
            and not getattr(v, "elts", None)
            and not getattr(v, "keys", None)):
        return True                                   # [] / {} / set()
    if isinstance(v, ast.Tuple):                      # ([], []) — the awgit shape
        return all(
            isinstance(e, (ast.List, ast.Dict, ast.Set))
            and not getattr(e, "elts", None) and not getattr(e, "keys", None)
            for e in v.elts
        ) and bool(v.elts)
    return False


# Sites HYG004 examined and deliberately did NOT count, with the reason. Printed on
# every run: an exemption nobody can see is indistinguishable from a rule that stopped
# firing, which is the failure this whole file exists to prevent.
_HYG004_EXEMPT_SITES: list[str] = []


def _returns_none(node: "ast.Return") -> bool:
    """True for `return` / `return None` — NOT for `return []` or `return 0`.

    The distinction is the whole point: `[]` and `{}` ARE answers ("no findings"), so a
    caller cannot tell them from a real clean result. `None` can be a sentinel, and
    whether it IS one is decided by `_none_means_dead` below.
    """
    v = node.value
    return v is None or (isinstance(v, ast.Constant) and v.value is None)


def _enclosing_func(mod: "ast.Module", target: "ast.AST") -> str:
    """Name of the function lexically containing `target`, or '' if module-level."""
    for fn in ast.walk(mod):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(n is target for n in ast.walk(fn)):
                return fn.name
    return ""


def _none_means_dead(mod: "ast.Module", func_name: str) -> bool:
    """True if some caller of `func_name` treats a None result as DEAD, not as clean.

    The shape asserted is the one this repo's checkers actually use:

        bad = tarball_violations(path)
        if bad is None:
            print("NOT VERIFIED: ...")
            return 2                     # or sys.exit(2)

    Deliberately narrow — it requires a real `is None` test whose branch exits 2 — so a
    function that merely returns None somewhere is NOT exempted. Intra-file only: a
    cross-module caller is not decidable from one AST, and guessing would hand out
    exemptions the evidence does not support.
    """
    if not func_name:
        return False

    bound: set[str] = set()
    for n in ast.walk(mod):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
            called = n.value.func
            if (getattr(called, "id", "") == func_name
                    or getattr(called, "attr", "") == func_name):
                bound |= {t.id for t in n.targets if isinstance(t, ast.Name)}
    if not bound:
        return False

    for node in ast.walk(mod):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (isinstance(test, ast.Compare)
                and len(test.ops) == 1 and isinstance(test.ops[0], ast.Is)
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value is None
                and isinstance(test.left, ast.Name)
                and test.left.id in bound):
            continue
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Return) and isinstance(inner.value, ast.Constant)
                    and inner.value.value == 2):
                return True
            if isinstance(inner, ast.Call):
                fn = inner.func
                is_exit = (getattr(fn, "id", "") == "exit"
                           or (getattr(fn, "attr", "") == "exit"
                               and getattr(getattr(fn, "value", None), "id", "") == "sys"))
                if is_exit and any(isinstance(a, ast.Constant) and a.value == 2
                                   for a in inner.args):
                    return True
    return False



# HYG004 baseline — checkers KNOWN to swallow a parse failure and report clean, pinned
# 2026-08-09. Keyed by FILE, not file:line: a line-keyed pin drifts on every unrelated
# edit above it and would false-positive its way into being muted. The gate fires when a
# NEW checker joins this list; the list itself must SHRINK, never grow.
#
# Two were fixed the day this rule was written, which is why they are absent:
# check_undefined_names' main analysis path (11 shipped service modules were invisible to
# it because a BOM made ast.parse raise) and check_async_blocking (same BOM blindness, so
# PQ010's blocking-call gate was clean on those same files). The rest are real and open.
_HYG004_BASELINE = {
    "check_capability_surfaced.py",
    "check_llm_facade_conformance.py",
    "check_local_call_signatures.py",
    "check_mcp_apps_contract.py",
    "check_nexus_client_contract.py",
    "check_python_quality.py",
    "check_service_registry_resolves.py",
    "check_undefined_names.py",
}

# HYG008 — a checker that talks to the container engine as `docker` ONLY.
#
# This fleet runs rootful podman in WSL2. A checker that shells `docker ps` does not
# report a smaller truth here, it reports NOTHING: every call fails, the tool exits 2,
# and the invariant it guards goes unwatched for as long as nobody reads the exit code.
# `check_container_import_errors.py` was found in exactly that state on 2026-08-13,
# minutes after a new rule was added to it — the rule could never have run.
#
# The fix is the ladder both check_lb_upstream_liveness.py and (now)
# check_container_import_errors.py use: PROBE for the engine, docker first so a box
# mid-cutover still works, podman-in-WSL second, and say which one answered.
#
# Pinned, not zero: 36 of the 64 engine-touching checkers were docker-only when this
# rule was written, and a gate that opens red gets bypassed rather than satisfied —
# which is exactly how this repo's per-file-ignores came to exist. The count must
# SHRINK. A checker newly hardcoding docker fails immediately; remediating one lowers
# the pin in the same commit.
# 36 -> 32 on 2026-08-15. One of those four is check_wal_retention_bounded.py,
# which was docker-only and therefore had NEVER judged the WAL invariant it was
# written for — every run returned NOT VERIFIED. It is exactly the state this
# rule's own comment describes, found by asking the fleet rather than the tool.
# 32 -> 5 on 2026-08-16: 32 checkers were ported to the shared ladder in
# `_container_engine.py` (import it; do not paste a fourth copy — three had already
# drifted, which is what HYG005 was reporting). The transform is
# `[*(_engine_prefix() or ["docker"]), ...]`, which adds the podman path and keeps
# each file's existing failure handling, so a port can never turn a dead gate into a
# falsely-clean one. Verified: 31 of the 32 self-tests pass; check_deploy_pending.py
# fails identically at HEAD (it never implemented --self-test) and is not a regression.
_HYG008_PIN = 0

# A docker string must be in COMMAND position — `["docker", ...]` or `("docker", ...)`.
# A bare `"docker"` matched anything, including `check_onboarding_funnel.py`'s topic
# set where it is a keyword for matching onboarding docs, never a command.
# The bracket form must open a COMMAND LIST, not index a mapping. Measured
# 2026-08-21: check_storage_topology.py was flagged for
# topo["planes"]["volumes"]["canonical"]["docker"] and
# .get("canonical", {}).get("docker") -- reading a CONFIG KEY named after the
# engine, never calling it. A lookbehind for an identifier, `]`, `)` or `.`
# separates run(["docker", ...]) from x["docker"] and y.get("docker").
_ENGINE_CALL_RE = re.compile(
    r"""(?<![\w\]\)])\[\s*["']docker["']"""
    r"""|(?<![\w.])\(\s*["']docker["']"""
    r"""|\bdocker\s+(?:ps|inspect|exec|logs)\b""")
# `_engine_subprocess` is check_rpc_pool_reachable.py's own (real) ladder. It was
# passing only because "podman" appeared in a COMMENT — once prose stopped counting,
# a genuinely-ported checker started failing, which is the wrong direction.
_ENGINE_LADDER_RE = re.compile(r"_engine_prefix|_engine_subprocess|def engine\(|podman")

#: Checkers whose docker calls run on a DIFFERENT host, over ssh. The local engine
#: ladder does not apply there and porting them would be actively wrong — the remote
#: cloud-edge box really does run docker. Each entry must carry a reason; the list
#: prints on every run so it cannot quietly grow, and it may only ratchet DOWN.
_HYG008_REMOTE_HOST = {
    "check_edge_capabilities.py":
        "docker runs on the remote cloud-edge host via ssh (_ssh_key/ssh+script)",
    "check_edge_session_store.py": "docker cp/exec run on the remote cloud-edge host via ssh",
    "check_docker_pull_path.py":
        "subject IS the Docker daemon's pull proxy (http.docker.internal:3128); "
        "podman would not exercise the path this gate exists to hold",
}


def _strip_comments_and_docstrings(src: str) -> str:
    """Drop comments and string literals so PROSE about docker is not read as docker.

    `check_build_headroom.py` names `docker ps` only in a docstring explaining an
    incident. Flagging the documentation of a defect as the defect is how a gate gets
    deleted rather than satisfied, so the analysis runs over code, not narrative.
    Command-position strings survive because they are re-matched separately below.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src  # unparseable: keep the raw text rather than silently seeing less
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                first = body[0].value
                for ln in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                    docstrings.add(ln)
    out = []
    for i, line in enumerate(src.splitlines(), start=1):
        if i in docstrings:
            continue
        out.append(line.split("#", 1)[0] if "#" in line else line)
    return "\n".join(out)


def _hyg12(trees: list[Path]) -> list[str]:
    """HYG012 - no checker module defines the same top-level function TWICE.

    Python keeps the LAST definition, so the first is silently unreachable. In this
    family that is not a style nit: the rules here are one function per rule id, and
    the second def takes the id AND the name with it.

    Measured on origin/develop 2026-08-20: check_site_nav_reachable.py had two
    functions called `check_nav006` -- the worker-URL rule had been renumbered 005 ->
    006 by one session while the route-directory rule already held 006 from another,
    and both were named after their id. main() calls both, with different signatures,
    so the whole checker died on

        TypeError: check_nav006() takes 0 positional arguments but 1 was given

    before a single rule ran. Seven live rules stopped asserting at once, and the
    file is wired in debt-invariants.yml, so what CI showed was a red job on a gate
    nobody had touched -- which reads as a flaky checker, not as seven dead rules.

    Two sessions renumbering in parallel is the ordinary way this happens, and
    neither of them is wrong on its own: the collision exists only in the union, and
    a merge resolves it CLEANLY because the two defs are hundreds of lines apart and
    conflict in nothing git can see. That is the whole reason for a static rule --
    the one thing that would have caught it is asking a parsed module whether it says
    a name twice.

    Scans `tree.body` only. A def nested inside `if`/`try` is the legitimate
    conditional-fallback idiom this repo uses throughout, and flagging it would flood
    -- which is how a rule gets switched off rather than satisfied.

    Opens at ZERO across 379 checkers, so it gates rather than ratchets: a new
    collision fails immediately instead of being absorbed into a pin.
    """
    out: list[str] = []
    for tree in trees:
        for f in sorted(tree.glob("check_*.py")):
            try:
                mod = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
            except (OSError, SyntaxError, ValueError):
                # Unreadable is HYG004's question, not this one. Saying nothing here
                # is right; saying CLEAN would be the bug that rule exists for.
                continue
            seen: dict[str, int] = {}
            for node in mod.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    seen[node.name] = seen.get(node.name, 0) + 1
            for name, count in sorted(seen.items()):
                if count > 1:
                    out.append(
                        f"HYG012 {f.name}: `{name}` is defined {count}x at module level -- "
                        "the later def SHADOWS the earlier one, so that rule can never run "
                        "and a signature mismatch kills the whole checker at import time"
                    )
    return out


def _hyg11(trees: list[Path]) -> list[str]:
    """HYG011 - every checker on disk is TRACKED BY GIT.

    HYG003 asks whether a checker NAMED somewhere exists on disk. This asks the
    inverse, which nothing was asking: does a checker that exists on disk exist
    in the REPOSITORY? An untracked checker is not a weak gate, it is a
    non-existent one -- absent from every clone, every CI job and every runner,
    while being perfectly present and passing for the person who wrote it.

    Measured 2026-08-18: 56 files under dev/tools were untracked, 24 of them
    `check_*.py`. One of those, check_tenant_site_health.py, reported two live
    HIGH violations the first time anything ran it (two customer backends with
    `tenant_id is None`) -- findings that had been sitting on a single disk,
    unable to reach anyone.

    Nothing else could see it: the file is on disk, so every local run passes,
    `git status` is clean once it is ignored or simply never added, and the tool
    imports and self-tests correctly. Same class as the untracked-package
    defect, applied to the gate
    family itself.
    """
    out: list[str] = []
    for tree in trees:
        names = sorted(p.name for p in tree.glob("check_*.py"))
        if not names:
            continue
        try:
            proc = subprocess.run(
                ["git", "ls-files", "--", *names],
                cwd=tree, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            # Could not ask git -> say so. An unanswerable question is never a pass.
            return [f"HYG011 NOT VERIFIED: could not ask git about {tree} "
                    f"({type(exc).__name__}: {exc})"]
        if proc.returncode != 0:
            return [f"HYG011 NOT VERIFIED: `git ls-files` failed in {tree} "
                    f"({(proc.stderr or '').strip()[:160]})"]
        tracked = {line.strip().rsplit("/", 1)[-1] for line in proc.stdout.splitlines()}
        for name in names:
            if name not in tracked:
                out.append(
                    f"HYG011 {tree.name}/{name}: on disk but NOT TRACKED by git -- it "
                    f"exists for you and for nobody else. No clone has it, no CI job "
                    f"can run it, and it will pass locally forever."
                )
    return out


def _hyg8(trees: list[Path]) -> list[str]:
    """HYG008 — engine-touching checkers with no podman path. Returns offenders."""
    out: list[str] = []
    for tree in trees:
        for f in sorted(tree.glob("check_*.py")):
            try:
                src = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if f.name in _HYG008_REMOTE_HOST:
                continue
            code = _strip_comments_and_docstrings(src)
            if not _ENGINE_CALL_RE.search(code):
                continue
            # Ask the RAW source, not the stripped copy. The ladder is spelled as
            # string literals (the ["podman", ...] candidate list), and the stripper
            # removes those -- so a file WITH a working ladder read as having none
            # while its ["docker"] subscript survived to be flagged. The stripper
            # exists to stop PROSE being read as a call; using it to look for
            # EXCULPATORY evidence inverts its purpose.
            if _ENGINE_LADDER_RE.search(src):
                continue
            out.append(f.name)
    return sorted(set(out))


def _hyg4(trees: list[Path]) -> list[str]:
    """HYG004 — a checker that swallows an unreadable input and reports CLEAN.

    THE PATTERN, measured three separate times on 2026-08-09 and each time it made a
    working gate blind rather than noisy:
      * check_undefined_names read files as plain utf-8, so a leading BOM raised
        SyntaxError and `except SyntaxError: return [], []` printed
        "OK: no unresolvable names" for 11 shipped service modules it never parsed —
        including the mesh fabric, which was hiding a guaranteed NameError;
      * sqlite_store_integrity scanned one tree while the service's databases lived in
        two others, so it ran clean over three unopenable stores (7158 rows recovered);
      * awgit capture returned [] for an unparseable file, and an empty node set diffs
        as DELETION — so a conflicted file was recorded as "every function deleted".
    Three instances is a class, not a coincidence, and the rule these tools already
    state is "exit non-zero when it CANNOT run — a probe that cannot emit a verdict is
    DEAD, never passing". `empty` and `unknown` are different answers.

    Flags an `except` handler catching a cannot-read exception whose body returns a
    clean/empty value with NO other action — no raise, no recording, no non-zero exit.
    A handler that logs AND records, or re-raises, or returns a sentinel, is fine.
    """
    out: list[str] = []
    exempt = _HYG004_EXEMPT_SITES
    exempt.clear()
    for tree in trees:
        for f in sorted(tree.rglob("check_*.py")):
            try:
                mod = ast.parse(f.read_text(encoding="utf-8-sig", errors="replace"))
            except SyntaxError:
                # This checker cannot parse a checker — that is itself an unknown, so
                # say so rather than passing over it (the very rule being enforced).
                out.append(f"{f.name}: could not be parsed by HYG004")
                continue
            for h in (n for n in ast.walk(mod) if isinstance(n, ast.ExceptHandler)):
                names = set()
                t = h.type
                for node in ast.walk(t) if t is not None else []:
                    if isinstance(node, ast.Name):
                        names.add(node.id)
                    elif isinstance(node, ast.Attribute):
                        names.add(node.attr)
                if not (names & _CANNOT_READ_EXC):
                    continue
                # Any escalation in the handler makes it honest.
                escalates = any(
                    isinstance(n, ast.Raise) for n in ast.walk(h)
                ) or any(
                    isinstance(n, ast.Call) and (
                        getattr(getattr(n, "func", None), "id", "") in ("exit", "SystemExit")
                        or getattr(getattr(n, "func", None), "attr", "") in (
                            "exit", "append", "add", "warning", "error")
                    )
                    for n in ast.walk(h)
                ) or any(
                    # Recording into a container (UNREADABLE[path] = why) is the
                    # docstring's "records" case — SUBSCRIPT targets only, so a
                    # plain `x = None; return x` still flags.
                    isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Subscript) for t in n.targets)
                    for n in ast.walk(h)
                )
                if escalates:
                    continue
                for n in h.body:
                    if not (isinstance(n, ast.Return) and _is_clean_return(n)):
                        continue
                    # `return None` is only a swallow if None means "no findings" HERE.
                    # A tool whose caller reads None as "could not judge" and exits 2 is
                    # doing exactly what this rule asks for, in the idiom the rule's own
                    # docstring recommends (a sentinel). Flagging it made a correct tool
                    # look like a defect on 2026-08-17 — check_package_entrypoints, whose
                    # own --self-test asserts an unreadable archive returns None and the
                    # caller exits 2. Baselining that would have been worse than the false
                    # positive: it would have pinned a NON-defect onto a must-shrink list.
                    if _returns_none(n) and _none_means_dead(mod, _enclosing_func(mod, h)):
                        exempt.append(f"{f.name}:{n.lineno}: None is the DEAD sentinel "
                                      f"here — a caller tests `is None` and exits 2")
                        continue
                    out.append(f"{f.name}:{n.lineno}: "
                               f"except {sorted(names & _CANNOT_READ_EXC)} returns "
                               f"CLEAN — unreadable input reported as no findings")
    return out



_MARKER_NAME = "canonical-deploy-root"


def _code_only(src: str) -> str:
    """`src` with whole-line `#` comments removed.

    FULL-LINE comments only, on purpose: a TRAILING `#` cannot be stripped without
    tracking string literals, and a naive attempt would cut real code containing a
    `#` in a string — hiding a genuine read, which is the expensive direction to be
    wrong in. This is enough for the measured shape, a file whose only mention of
    the marker is an explanatory comment.
    """
    return "".join(
        line + "\n"
        for line in (src or "").splitlines()
        if not line.lstrip().startswith("#")
    )


def _marker_parse_violations(tools_dir: Path) -> list[str]:
    """HYG006 — a tool that reads the deploy-root marker WHOLE instead of line-wise.

    The marker carries explanatory comment lines before the path. Reading it with
    `read_text().strip()` therefore yields a string that is not a directory, the
    is_dir()/exists() test fails, and the tool falls back to the WORKING TREE —
    silently operating on the wrong root. Nothing errors; the tool just answers
    about a different tree than the fleet deploys from.

    Measured 2026-08-10 in provision_quadlet_env.py: it resolved credentials from
    D:'s .env (49 names) instead of the deploy root's (53) and refused to
    provision MinIO for want of a password sitting in the file it was not
    reading. check_image_store_integrity.py had the identical bug.

    LIMITATION, stated because a checker that oversells itself is worse than a
    narrow one: this is a FILE-LEVEL heuristic. It asks whether the file contains
    a comment-skipping idiom at all, so a tool that parses the marker correctly in
    one place and carelessly in another passes. It reliably catches the real shape
    — a tool that never handles comments anywhere, which is how BOTH live
    instances looked — and deliberately does not attempt dataflow it cannot do
    accurately.

    BOTH correct idioms are accepted — `startswith("#")` skipping and
    `split("#", 1)[0]`. An earlier version of this detector knew only the first
    and produced a FALSE POSITIVE on check_baked_code_staleness.py, which was
    correct all along; a rule that cries wolf gets switched off.
    """
    out: list[str] = []
    for f in sorted(tools_dir.glob("*.py")):
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # ASK THE CODE, NOT THE PROSE.
        #
        # This tested the RAW source, so a file that merely NAMES the marker in a
        # comment became a candidate — and a file that never reads it has no
        # comment-skipping idiom either, so it was then reported as parsing the
        # marker wrongly. Measured 2026-08-22: `run_fleet_gates_from_host.py` was
        # flagged for a ONE-LINE COMMENT explaining why a HOST_ONLY gate needs the
        # marker. It does not read it at all. That is the failure this family names
        # everywhere else — flagging the documentation of a defect as the defect —
        # arriving inside the detector that names it.
        #
        # Only the MENTION test is de-commented. The idiom test below must keep
        # reading raw `src`, because the idioms it looks for (`startswith("#")`,
        # `split("#", 1)[0]`) contain a `#` themselves and any comment stripping
        # would destroy them — turning a correct tool into a reported violation,
        # which is the same cry-wolf failure pointed the other way.
        if _MARKER_NAME not in _code_only(src):
            continue
        linewise = ('startswith("#")' in src or "startswith('#')" in src
                    or 'split("#", 1)[0]' in src or 'split("#",1)[0]' in src)
        if not linewise:
            out.append(f"{f.name}: reads the {_MARKER_NAME} marker without "
                       f"skipping its comment lines — falls back to the working "
                       f"tree and silently uses the wrong root")
    return out



# HYG009 baseline — checkers that are DOCUMENTED or WIRED but which git is not tracking, so
# they resolve to nothing in every clone and every CI run. Measured 2026-08-15: 37 check_*.py
# under dev/tools were untracked and THESE are the ones a workflow or routine actually names.
# The fix for each is a commit, not an allowlist entry. The pin exists because opening red
# fleet-wide gets a gate bypassed rather than satisfied — it must only ever SHRINK, and
# landing a fix without lowering it fails, so an unratcheted win cannot be given back.
HYG009_PIN = 0

def _tracked_set(root: Path) -> set[str] | None:
    """Repo-relative posix paths git is TRACKING, or None when git cannot answer.

    None (not an empty set) when this is not a git work tree: an empty set would read as
    "nothing is tracked" and flag every checker in the repo, which is the flood that gets a
    gate switched off rather than satisfied.
    """
    out = subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if out.returncode != 0:
        return None
    return {ln.strip().replace("\\", "/") for ln in out.stdout.splitlines() if ln.strip()}


def _untracked_live(root: Path, names: set[str], resolve, trees) -> list[str]:
    """HYG009 -- a documented-or-wired checker that git is not tracking.

    HYG002/HYG003 ask whether a checker EXISTS ON DISK, and on the machine that wrote it the
    answer is always yes. That is not the question CI asks. Measured 2026-08-15: 37 check_*.py
    in dev/tools were untracked, and THIRTEEN of them were named by a workflow or a routine --
    including check_wgsl_compiles.py, wired in both. Those gates resolve to nothing in every
    clone and every CI run while this checker printed HYGIENE: ok, because it looked at a
    filesystem instead of at the repository.

    Same class as the lease plane that prevented nothing for weeks because its
    source never reached the working branch, and the same lesson: a file is not
    tracked because you wrote it, it is tracked when `git ls-files` says so.
    """
    tracked = _tracked_set(root)
    if tracked is None:
        return []
    out: list[str] = []
    for name in sorted(names):
        found = resolve(name, trees)
        if found is None:
            continue                      # HYG002/HYG003 already own "missing on disk"
        try:
            rel = found.relative_to(root).as_posix()
        except ValueError:
            continue
        if rel not in tracked:
            out.append(name)
    return out


#: HYG013 - agent-CONTEXT files that git is not tracking.
#:
#: HYG009 asks this of checkers. This asks it of the files that shape how every
#: session BEHAVES: configuration files load into agent context, hook files
#: gate real actions, skill files are invoked by name.
#:
#: Measured: configuration files that define session behavior were untracked
#: on a working branch where many files had been deleted hours earlier, in a
#: tree where 619 tracked files had been deleted hours earlier, one `git clean`
#: from gone.
#:
#: The failure is INVISIBLE from the machine that wrote it: the rule loads, the
#: hook fires, the skill resolves. It is absent in every clone and in CI, so a
#: rule "everyone follows" is followed only here -- indistinguishable from a rule
#: nobody wrote. Same lesson as HYG009: a file is not tracked because you wrote
#: it, it is tracked when `git ls-files` says so.
#:
#: Pinned at 0 and ratcheting DOWN only. The fix for each finding is a COMMIT by
#: whoever wrote it, never an entry here.
#:
#: Carried the id HYG011 before the develop catch-up merge (PR #5952); develop
#: had independently used HYG011 for a different rule, so this took a free id.
# Configuration directories that must remain tracked
HYG013_DIRS = (".config", ".hooks", ".skills")
HYG013_PIN = 0


def _hyg13(root: Path) -> list[str] | None:
    """HYG013 -- (paths), or None when git cannot answer (never an empty list).

    None, never []: an empty list reads as "everything is tracked", which is the
    most reassuring possible rendering of "I could not look" -- the exact shape
    this rule exists to catch one directory over.
    """
    tracked = _tracked_set(root)
    if tracked is None:
        return None
    found = []
    for d in HYG013_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(root).as_posix()
            if "__pycache__" in rel or rel.endswith(".pyc"):
                continue
            if rel not in tracked:
                found.append(f"HYG013 {rel}: agent context on disk but NOT TRACKED by git")
    return sorted(found)


#: HYG014 - a container-engine probe that reports failure as an EMPTY COLLECTION.
#:
#: Measured 2026-08-22: SIX instances found by hand in one session, in the very
#: tools written to catch fleet problems. Each turned "could not ask" into "the
#: answer is zero", and for a gate those are opposite verdicts -- a zero is a
#: clean fleet, an unanswered engine is a scan that never happened.
#:
#: Pinned at the measured backlog and ratcheting DOWN only: a gate that opens red
#: gets bypassed rather than satisfied.
#: 12 measured 2026-08-22 across 6 files, including FOUR in
#: check_deploy_invariants.py. Ratchets DOWN only.
HYG014_PIN = 12

#: Trees whose job is to JUDGE the fleet. A false "nothing found" here is a
#: silent gate, which is the failure this whole file exists to prevent.
#:
#: Held as path COMPONENTS, not joined literals: this file is mirrored verbatim
#: into the public skills pack (HYG005 demands the copies match byte for byte),
#: and a joined monorepo path is exactly what that pack's boundary scan rejects.
#: Same idiom the rest of this module already uses.
HYG014_TREES = (("AitherOS", "dev", "tools"), ("AitherOS", "lib", "routines"))

_ENGINE_TOKENS = ("podman", "docker")
_RC_TOKENS = ("returncode", "rc", "code", "status")


def _hyg14_empty_literal(node: ast.AST) -> str | None:
    """The name of the empty collection this returns, or None."""
    if isinstance(node, ast.List) and not node.elts:
        return "[]"
    if isinstance(node, ast.Dict) and not node.keys:
        return "{}"
    if isinstance(node, ast.Tuple) and not node.elts:
        return "()"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id in ("set", "list", "dict", "tuple") and not node.args:
            return f"{node.func.id}()"
    return None


def _hyg14_mentions_engine(fn: ast.AST) -> bool:
    """Does this function shell a container-engine command?

    A string CONSTANT equal to or starting with podman/docker anywhere in the
    function. Deliberately loose on where it appears (argv list, f-string,
    helper call) and strict on what it is, so a comment or a variable merely
    NAMED docker does not qualify.
    """
    for n in ast.walk(fn):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            v = n.value.strip().lower()
            if v in _ENGINE_TOKENS or v.startswith(("podman ", "docker ")):
                return True
    return False


def _hyg14_is_rc_test(test: ast.AST) -> bool:
    """Is this `if` testing a subprocess return code?"""
    for n in ast.walk(test):
        if isinstance(n, ast.Attribute) and n.attr in _RC_TOKENS:
            return True
        if isinstance(n, ast.Name) and n.id in _RC_TOKENS:
            return True
    return False


def _hyg14(root) -> list[str] | None:
    """HYG014 -- (findings), or None when no tree could be read.

    None, never []: reporting "no violations" from a walk that read nothing is
    the exact defect being checked, one level up.
    """
    findings: list[str] = []
    scanned = 0
    for parts in HYG014_TREES:
        base = root
        for seg in parts:
            base = base / seg
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*.py")):
            try:
                mod = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
            except (OSError, SyntaxError):
                continue
            scanned += 1
            rel = f.relative_to(root).as_posix()
            for fn in ast.walk(mod):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not _hyg14_mentions_engine(fn):
                    continue
                for node in ast.walk(fn):
                    if not isinstance(node, ast.If) or not _hyg14_is_rc_test(node.test):
                        continue
                    for stmt in node.body:
                        if not isinstance(stmt, ast.Return) or stmt.value is None:
                            continue
                        lit = _hyg14_empty_literal(stmt.value)
                        if lit:
                            findings.append(
                                f"HYG014 {rel}:{stmt.lineno} {fn.name}() returns "
                                f"{lit} when the container engine fails - an empty "
                                f"collection is indistinguishable from a real zero, "
                                f"and for a gate those mean opposite things. Return "
                                f"None or raise."
                            )
    if scanned == 0:
        return None
    return sorted(set(findings))


def _collect(root: Path):
    """Read every source once and return the verdict buckets.

    Returns (hyg1, hyg2, hyg3, hyg5, report) where hyg1/2/3/5 are violation
    lists and report is a dict of non-gating stats.
    """
    trees = candidate_trees(root)
    tree = trees[0] if trees else None
    rules = root / LAYOUT["rules_doc"] if LAYOUT["rules_doc"] else None
    workflow = root / ".github/workflows/debt-invariants.yml"
    routines_dir = root / LAYOUT["routines_dir"] if LAYOUT["routines_dir"] else None
    probe = root / LAYOUT["debt_probe"] if LAYOUT["debt_probe"] else None

    if tree is None or rules is None or not rules.is_file() or not workflow.is_file():
        raise RuntimeError(
            "gate tree=%s rules=%s workflow=%s — a source is missing" % (
                tree, bool(rules and rules.is_file()), workflow.is_file()
            )
        )

    doc = documented_gates(rules)
    wired = (wired_in_workflow(workflow)
             | wired_in_routines(routines_dir, probe)
             | wired_in_host_gates(root))

    hyg1: list[str] = []
    hyg2 = sorted(n for n in doc if resolve(n, trees) is None)
    hyg3 = sorted(n for n in wired if resolve(n, trees) is None)
    # HYG011 rides in the same list: both findings mean "this checker is not
    # really there", and each message carries its own rule id. Kept out of a
    # 12th tuple slot because every consumer of this return would have to be
    # touched to add one, which is how a rule gets left unwired.
    # HYG012 rides here for the same reason HYG011 does: all three findings mean
    # "this checker is not really there". A shadowed rule is present on disk and
    # absent at runtime, which is the same outcome as a missing file.
    hyg3 = hyg3 + _hyg11(trees) + _hyg12(trees)
    hyg9 = _untracked_live(root, doc | wired, resolve, trees)
    hyg13 = _hyg13(root)
    hyg14 = _hyg14(root)
    hyg15 = _hyg015(root)

    for name in sorted(doc | wired):
        found = resolve(name, trees)
        if found is None:
            continue
        src = found.read_text(encoding="utf-8", errors="replace")
        if "--self-test" not in src:
            hyg1.append(name)

    all_checkers = sorted(
        p.name for p in tree.rglob("check_*.py") if p.is_file()
    )
    no_selftest_tree = []
    for n in all_checkers:
        f = resolve(n, trees)
        if f is None:
            continue
        if "--self-test" not in f.read_text(encoding="utf-8", errors="replace"):
            no_selftest_tree.append(n)

    hyg4 = _hyg4(trees)
    hyg5 = _hyg5(root)

    report = {
        "total_checkers": len(all_checkers),
        "no_selftest_tree": no_selftest_tree,
        "wired_nowhere": sorted(
            n for n in all_checkers if n not in doc and n not in wired
        ),
        "wired_but_undocumented": sorted(n for n in wired if n not in doc),
        "documented_count": len(doc),
        "wired_count": len(wired),
    }
    hyg6 = _marker_parse_violations(root / 'AitherOS' / 'dev' / 'tools')
    hyg7 = _hyg7(root, trees)
    hyg8 = _hyg8(trees)
    hyg10 = _hyg10(root)
    return (hyg1, hyg2, hyg3, hyg4, hyg5, hyg6, hyg7, hyg8, hyg9, hyg10,
            hyg13, hyg14, hyg15, report)


#: HYG010 — Veil test files reachable by NO gating CI invocation. Measured 2026-08-17:
#: 148 of 150 (cross-checked against `npx jest --listTests`, which reports 1 file for the
#: deploy gate's pattern out of 156). Pinned so it can only ratchet DOWN; a rise means
#: someone added tests to a tree nothing gates, which is what this rule exists to end.
#:
#: 148 -> 120 later the same day, and the way it moved is the point. A new
#: `components/os/__tests__` suite pushed the count to 149 — the rule catching the person
#: who had just added a test. The fix is never to raise the pin: it is to make the tests
#: GATE. deploy-veil.yml's --testPathPattern now includes that whole directory, which
#: turned out to cover 28 OTHER files that were also running nowhere. All 32 suites there
#: were green when it was widened (262/262 on the develop base), so the apex deploy now
#: gates on them; if one goes red the publish stops, which is exactly what a gate is for.
#: 132 -> 106 on 2026-08-19: deploy-veil's --testPathPattern now also gates
#: `src/lib/__tests__`, 26 suites that were executing nowhere that could go red.
#: TWO files there are deliberately excluded IN THE REGEX (a negative lookahead,
#: not --testPathIgnorePatterns): `bonsai-mobile-gate` and `bonsai-model-sizing`
#: are RED today, and gating a known-red suite blocks every publish. The
#: exclusion is written into the pattern because this checker parses
#: --testPathPattern ONLY — expressing it as an ignore-pattern would leave the
#: rule counting both files as gated, i.e. it would report 26 files newly
#: protected when 24 were. An overstated ratchet is worse than no ratchet.
#: 106 -> 105 on 2026-08-19: `bonsai-model-sizing` was fixed and re-admitted to
#: deploy-veil's pattern, so only `bonsai-mobile-gate` is still excluded — and
#: that one is an UNTRACKED file another session is still writing, not ours to
#: repair. The exclusion shrinks as the suites go green rather than being
#: permanent.
#: 105 -> 104 on 2026-08-19: the last exclusion is GONE. bonsai-mobile-gate
#: passes now that gpuSizeCeilingMb caps on mobile, so deploy-veil's pattern
#: carries no lookahead at all and every file under lib/__tests__ gates.
#: 104 -> 101 on 2026-08-21. deploy-veil.yml carried TWO --testPathPattern flags
#: on one jest command; jest takes the LAST, so the second silently overrode the
#: first and dropped `lib/__tests__` -- reverting the 132 -> 106 win recorded
#: above on 08-19 and taking the count back up to 110. Collapsed to their UNION
#: (110 -> 105), then added lib/model-planner/__tests__ (105 -> 101), a
#: React-free pure-logic suite.
#: NOT widened further on purpose: the rest of the suite has known pre-existing
#: failures (#895) and a red deploy-veil freezes aitherium.com.
#: RATCHETED 101 -> 63 on 2026-08-22. The win was already on disk and unbanked:
#: the tool had been printing "ratchet: lower HYG010_UNGATED_PIN to 63 in this
#: commit" on every run, and nobody could see it because this checker itself was
#: DEAD (its layout declared no `rules_doc`, so it exited 2 before judging
#: anything). An unratcheted win is silently given back -- which is the whole
#: reason these pins ratchet DOWN only. Measured stable at 63 across consecutive
#: runs before banking, because this tree churns under concurrent sessions and
#: pinning to a number caught mid-flight would fabricate CI failures.
HYG010_UNGATED_PIN = 15

#: A step that tolerates its own failure is not a gate. Same reasoning as `continue-on-error`
#: on a required check in check_workflow_parity (gate 1j).
#: The `-?` is load-bearing: `continue-on-error` is valid YAML both as the FIRST key of a
#: step (`- continue-on-error: true`) and as a later one (bare, indented). The first
#: spelling was missed until the self-test caught it, and missing it counts a tolerated
#: step as a gate — i.e. it reports coverage that does not exist, which is this rule's own
#: failure mode turned on itself.
_CONTINUE_ON_ERROR = re.compile(r"^\s*-?\s*continue-on-error:\s*true", re.M)


def _hyg10(root: Path) -> "tuple[list[str], int, int] | None":
    """HYG010 — a Jest test file that no GATING CI invocation runs.

    🚨 THIS IS THE RULE THAT EXPLAINS A WHOLE CLASS OF SHIPPED DEFECT.

    Measured 2026-08-17 in AitherVeil: **156 test files, of which 2 gate anything.**

      * `deploy-veil.yml` runs
        `--testPathPattern="src/(components/marketing|components/os/apps/greeter)"`,
        which matches exactly ONE file — and the `components/os/apps/greeter` half matches
        NOTHING, because greeter's tests live in `src/components/os/__tests__/`, not beside
        the component. The step's own comment names greeter as protected. It is not.
      * `ci.yml` runs the full suite with `continue-on-error: true` ("pre-existing failures
        tracked in #895"), so it cannot fail a build, plus one gating single-file run.

    So 154 files execute nowhere that can go red. Among them were `brain-breaker-escape`
    and `brain-picker-guidance` — written specifically to stop an in-browser-brain dead
    end — and a browser-brain dead end duly shipped and reached the owner. Four of those
    suites were ALSO failing to load outright (an unmapped `calendar-kit` subpath) for an
    unknown period, and nothing anywhere went red, because nothing ran them.

    A scoped gate is a legitimate choice — `deploy-veil` deliberately does not want a
    pre-existing red elsewhere to block publishing. What is not legitimate is that the
    scope is invisible: the count of what it excludes was written nowhere, so it drifted
    from "a subset" to "almost everything" with no moment at which anyone decided that.

    Returns (violations, ungated_count, total) or None when it could not judge.
    """
    app_rel = LAYOUT.get("jest_app")
    if not app_rel:
        return None                      # NOT APPLICABLE in a copy with no jest app
    veil = root / app_rel
    wf_dir = root / ".github" / "workflows"
    if not veil.is_dir() or not wf_dir.is_dir():
        return None

    tests = [
        p for p in veil.rglob("*.test.*")
        if p.suffix in {".ts", ".tsx", ".js", ".jsx"}
        and "node_modules" not in p.parts and ".next" not in p.parts
    ]
    if not tests:
        return None

    # Every jest invocation, with the gating question answered per STEP. A `run:` block is
    # non-gating when its own step carries continue-on-error; the cheap approximation is the
    # ~12 lines above the invocation, which is where that key sits in these files.
    patterns: list[str] = []
    saw_invocation = False
    for wf in sorted(wf_dir.glob("*.yml")):
        try:
            src = wf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if "npm test" not in line and "npx jest" not in line and " jest " not in line:
                continue
            saw_invocation = True
            preamble = "\n".join(lines[max(0, i - 12):i + 1])
            if _CONTINUE_ON_ERROR.search(preamble):
                continue                      # tolerated failure — not a gate
            # The invocation may continue onto following lines (a `>-` block).
            blob = "\n".join(lines[i:i + 4])
            m = re.search(r"--testPathPattern=?[\"' ]([^\"'\n]+)", blob)
            if m:
                patterns.append(m.group(1))
                continue
            # A POSITIONAL path is a scope restriction too, and missing that is how this
            # rule first reported a clean 0: `npx jest src/__tests__/x.test.ts` carries no
            # --testPathPattern, so it read as "the whole suite is gated" and the rule
            # asserted nothing at all. A checker that mis-parses its input into a PASS is
            # the precise failure this family exists to catch, so it is written down here.
            positional = re.findall(r"(?<![\w=/-])((?:src|dev|tests?)/[\w./-]+)", blob)
            if positional:
                patterns.extend(re.escape(q) for q in positional)
            else:
                patterns.append("")           # genuinely unscoped => the whole suite gates
    if not saw_invocation:
        return None

    if any(p == "" for p in patterns):
        ungated: list[Path] = []
    else:
        compiled = []
        for p in patterns:
            try:
                compiled.append(re.compile(p))
            except re.error:
                continue
        ungated = [
            t for t in tests
            if not any(c.search(t.relative_to(veil).as_posix()) for c in compiled)
        ]

    n = len(ungated)
    out: list[str] = []
    if n > HYG010_UNGATED_PIN:
        out.append(
            f"HYG010 {n} test file(s) in {app_rel} are run by NO gating CI invocation "
            f"(pin {HYG010_UNGATED_PIN}, of {len(tests)} total). A test that cannot fail a "
            f"build is not a gate. Widen a gating --testPathPattern, or drop a "
            f"continue-on-error, and lower the pin in the same commit."
        )
    return out, n, len(tests)


def _hyg7(root: Path, trees: list[Path]) -> list[str]:
    """HYG007 — a deploy-playbook phase gate must name a checker that EXISTS.

    Why this is a gate and not a convention
    ---------------------------------------
    the deploy phase files drive the fleet orchestrator, and each phase declares
    `gate.tool`. If that tool does not exist on disk the phase does not fail loudly -- the
    orchestrator finds nothing to run, and the phase reads as SATISFIED. A gate that names a
    missing tool therefore ALWAYS PASSES, which is strictly worse than having no gate: the
    playbook reports a verified deployment it never verified.

    Added 2026-08-11, when the phases were authored by agents. The rule "never invent a
    checker" was given to them as an INSTRUCTION, and an instruction is not an assertion --
    the same reasoning that turned the python-quality rules into check_python_quality.py
    after one of seven was found actually enforced. A later rename of any check_*.py would
    also silently hollow out every phase that gated on it.

    Skipped cleanly when the phases tree is absent (an adopted repo has none), which is a
    correct skip rather than a pass-by-omission.
    """
    violations: list[str] = []
    phases = root / "AitherOS" / "config" / "deploy" / "phases"
    if not phases.is_dir():
        return violations
    try:
        import yaml  # noqa: PLC0415 -- optional dep; absence must not crash the whole gate
    except ImportError:
        # Cannot parse => cannot judge. Surfaced as a violation rather than silence, because
        # "I could not look" must never render as "nothing is wrong" (HYG004's whole lesson).
        return ["(pyyaml missing — phase gate tools NOT VERIFIED)"]

    for f in sorted(phases.glob("*.yaml")):
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8", errors="replace")) or {}
        except Exception:  # noqa: BLE001 -- an unparseable phase is itself a finding
            violations.append(f"{f.name}: unparseable YAML — gate NOT VERIFIED")
            continue
        # `gate:` appears in BOTH shapes across the authored phases: a mapping with an
        # explicit `tool:`, and a free-text string describing the command. A first version
        # of this rule assumed the mapping and crashed on the string form -- caught by its
        # own negative control, which is the only reason it is not silently skipping those
        # files today. Handle both; anything else is a finding, not an exception.
        gate = doc.get("gate")
        tool = None
        if isinstance(gate, dict):
            # orchestrate_fleet.py reads gate["tool"] (line ~250). Phases authored later
            # declare the checker under gate["name"] instead, so the orchestrator resolves
            # None and RUNS NOTHING -- the phase passes without ever being verified.
            # Measured 2026-08-11: 7 of 11 phases, INCLUDING 08-inference-engine and
            # 09-embeddings-boot, whose gate is the DGX memory headroom check that exists
            # specifically to stop a model service starting into a starved pool. A grep for
            # the checker NAME finds it in all of them and looks correct; only asking the
            # key the orchestrator actually reads exposes it. Assert `tool`, and report a
            # `name`-only gate as the silent-pass defect it is.
            tool = gate.get("tool")
            if not tool and gate.get("name"):
                violations.append(
                    f"{f.name}: gate declares '{gate.get('name')}' under `name`, but "
                    f"orchestrate_fleet.py reads `gate.tool` — this gate NEVER RUNS and "
                    f"the phase always passes"
                )
                continue
        elif isinstance(gate, str):
            m = re.search(r"(check_[A-Za-z0-9_]+\.py)", gate)
            tool = m.group(1) if m else None
            if tool is None:
                continue  # a prose gate naming no checker: an inline command, allowed
        if not tool:
            # A phase with no gate cannot fail. That is the defect this family exists for.
            violations.append(f"{f.name}: phase declares NO gate.tool — it can never fail")
            continue
        if not str(tool).endswith(".py"):
            continue  # an inline command, deliberately allowed; nothing to resolve
        if resolve(str(tool), trees) is None:
            violations.append(
                f"{f.name}: gate.tool '{tool}' does not exist on disk — this phase "
                f"ALWAYS PASSES"
            )
    return violations


#: HYG015 -- pinned at ZERO because it CLOSED to zero in the commit that added it.
#: A new orphaned assertion is a new hole, not a backlog item.
HYG015_PIN = 0


def _hyg015_banking_helpers(fn: "ast.FunctionDef") -> set:
    """Names of nested helpers in `fn` that BANK a failure into a counter."""
    names = set()
    for sub in ast.walk(fn):
        if isinstance(sub, ast.FunctionDef) and sub is not fn:
            if any(isinstance(n, (ast.AugAssign, ast.Nonlocal))
                   for n in ast.walk(sub)):
                names.add(sub.name)
    return names


def _hyg015_counter_names(fn: "ast.FunctionDef", helpers: set) -> set:
    """Names the banking helpers increment — the self-test's failure counter."""
    names = set()
    for sub in ast.walk(fn):
        if not (isinstance(sub, ast.FunctionDef) and sub.name in helpers):
            continue
        for n in ast.walk(sub):
            if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):
                names.add(n.target.id)
            elif isinstance(n, ast.Nonlocal):
                names.update(n.names)
    return names


def _hyg015_verdict_lines(fn: "ast.FunctionDef", helpers: set) -> list:
    """Lines where `fn` returns its COUNTER VERDICT (`if bad: return 1`).

    🚨 THREE FALSE POSITIVES, AND THE RULE SHIPPED WITH ALL THREE.
    A naive "any `return 1` in the function" reported 3 findings on 2026-08-23
    and **every one was wrong** — it was about to send someone to "fix" three
    perfectly healthy checkers, which is how a gate gets deleted rather than
    satisfied ([[gate-invented-its-own-violations]] is this same trap seen from
    the other side). Each cause is separate and each is guarded here:

      1. `return True` MATCHES `value == 1` in Python (bool is an int
         subclass), so `deploy_veil_pages_direct`'s nested predicate returning
         True read as a failure verdict. Hence `type(...) is int`.
      2. An early abort in an EXCEPT handler (`except DeadProbeError: print
         FAIL; return 1`) is a legitimate DEAD exit, not a verdict — the arms
         "after" it never run at all when it fires. Two checkers, and one of
         them is `check_rented_gpu_reaped`, the GPU-billing gate.
      3. A `return 1` inside a NESTED function is not `fn`'s verdict.

    So a verdict is specifically: a `return <int 1>` inside an `if` whose test
    mentions the counter the banking helper increments, in `fn`'s own body.
    """
    counters = _hyg015_counter_names(fn, helpers)
    if not counters:
        return []
    nested = {id(n) for sub in ast.walk(fn)
              if isinstance(sub, ast.FunctionDef) and sub is not fn
              for n in ast.walk(sub)}
    lines = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.If) or id(node) in nested:
            continue
        if not any(isinstance(t, ast.Name) and t.id in counters
                   for t in ast.walk(node.test)):
            continue
        for st in ast.walk(node):
            if (isinstance(st, ast.Return) and isinstance(st.value, ast.Constant)
                    and type(st.value.value) is int and st.value.value == 1):
                lines.append(st.lineno)
    return lines


def _hyg015(root) -> "list[str] | None":
    """HYG015 -- assertions stranded AFTER a self-test's failure verdict.

    HYG001 asserts a ``--self-test`` EXISTS. It cannot ask whether the verdict
    is HONEST, and that is a different hole: a self-test whose
    ``if bad: return 1`` sits MID-FUNCTION banks every later ``ck(...)`` into a
    counter nothing reads again, then falls through to an unconditional
    "SELF-TEST PASSED" / return 0.

    **Every ordinary run looks perfect** -- all arms print, the banner prints,
    exit 0. The tell appears only under MUTATION: break the thing an orphaned
    arm covers and you get ``FAIL <that arm>`` followed by ``SELF-TEST PASSED``
    and exit 0. So the arms are present, printing, and unable to fail the run,
    which is precisely the state a self-test exists to rule out.

    Found 2026-08-23 in ``lambda_box.py`` while mutation-checking a new arm, and
    the shape was not unique: three more checkers had it, stranding **44**
    assertions between them -- including ``check_rented_gpu_reaped.py``
    (11 arms), the gate that decides whether a rented GPU is still billing.

    🚨 **The discriminator is what makes this shippable.** The obvious detector
    -- "any call after the fail-return" -- reports **291 of 770** files here,
    because ``print("SELF-TEST PASSED")`` legitimately follows every verdict. A
    rule that floods gets switched off (that is how this repo's per-file-ignores
    came to exist). Only a call to the function's OWN banking helper counts:
    that narrows it to **3**.

    Returns findings, or None when no tree could be read -- reporting "no
    violations" from a walk that read nothing is this file's own subject.
    """
    findings: list[str] = []
    scanned = 0
    for parts in HYG014_TREES:
        base = root
        for seg in parts:
            base = base / seg
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*.py")):
            try:
                mod = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
            except (OSError, SyntaxError):
                continue
            scanned += 1
            for fn in ast.walk(mod):
                if not isinstance(fn, ast.FunctionDef):
                    continue
                if "self_test" not in fn.name:
                    continue
                helpers = _hyg015_banking_helpers(fn)
                if not helpers:
                    continue
                fails = _hyg015_verdict_lines(fn, helpers)
                if not fails:
                    continue
                first = min(fails)
                orphan = [n.lineno for n in ast.walk(fn)
                          if isinstance(n, ast.Expr)
                          and isinstance(n.value, ast.Call)
                          and isinstance(n.value.func, ast.Name)
                          and n.value.func.id in helpers
                          and n.lineno > first]
                if orphan:
                    findings.append(
                        f"{f.name}::{fn.name}: verdict returns at L{first}, "
                        f"{len(orphan)} assertion(s) after it (L{min(orphan)}"
                        f"-L{max(orphan)}) can never fail the run — move the "
                        f"`if bad: return 1` to the END")
    if not scanned:
        return None
    return findings


def run(root: Path, show_all: bool) -> int:
    try:
        (hyg1, hyg2, hyg3, hyg4, hyg5, hyg6, hyg7, hyg8, hyg9, hyg10,
         hyg13, hyg14, hyg15, report) = _collect(root)
    except RuntimeError as exc:
        print(f"CANNOT RUN: {exc}", file=sys.stderr)
        return 2

    findings = False
    for code, label, items in (
        ("HYG001", "documented-or-wired checkers with no --self-test", hyg1),
        ("HYG002", "documented checkers missing on disk", hyg2),
        ("HYG003", "wired checkers missing on disk", hyg3),

        ("HYG004", "checkers that report CLEAN on input they could not read (NEW)",
         [x for x in hyg4 if x.split(":")[0] not in _HYG004_BASELINE]),
        ("HYG005", "discipline copies drifted across delivery homes", hyg5),
        ("HYG006", "tools parsing the deploy-root marker whole (wrong root)", hyg6),
        ("HYG007", "deploy-playbook phase gates naming a checker that does not exist "
                   "(such a phase ALWAYS PASSES)", hyg7),
        ("HYG008", f"docker-only checkers — inert on this podman fleet "
                   f"(pin {_HYG008_PIN}, must shrink)",
         hyg8 if len(hyg8) > _HYG008_PIN else []),
        ("HYG010", f"jest tests run by NO gating CI invocation "
                   f"(pin {HYG010_UNGATED_PIN}, must shrink)",
         hyg10[0] if hyg10 else []),
        # None means git could not answer -- reported as a violation rather
        # than as "nothing untracked", because silence is not a pass.
        ("HYG013", f"agent-context files git is NOT tracking "
                   f"(pin {HYG013_PIN})",
         (["HYG013 NOT VERIFIED: git could not answer for this tree"]
          if hyg13 is None else
          (hyg13 if len(hyg13) > HYG013_PIN else []))),
        # Same contract as HYG013: None is a violation, not a clean run. That is
        # the very defect this rule checks for, so reporting it any other way
        # would make the rule an instance of itself.
        ("HYG014", f"engine probes returning an EMPTY COLLECTION on failure "
                   f"(pin {HYG014_PIN})",
         (["HYG014 NOT VERIFIED: no tool tree could be read"]
          if hyg14 is None else
          (hyg14 if len(hyg14) > HYG014_PIN else []))),
        # Same None-is-a-violation contract as HYG013/HYG014.
        ("HYG015", f"self-test assertions stranded after the verdict — present, "
                   f"printing, and UNABLE to fail the run (pin {HYG015_PIN})",
         (["HYG015 NOT VERIFIED: no tool tree could be read"]
          if hyg15 is None else
          (hyg15 if len(hyg15) > HYG015_PIN else []))),
    ):
        if items:
            findings = True
            _safe_print(f"{code}: {label}:")
            for n in items:
                _safe_print(f"  - {n}")

    # The allowlist prints unconditionally: an exemption nobody re-reads is how a
    # gate quietly stops asserting. It may only ratchet DOWN.
    _safe_print(f"HYG005 exempt (public-boundary conflict) — {len(_HYG005_BOUNDARY_EXEMPT)}:")
    for _name, _why in sorted(_HYG005_BOUNDARY_EXEMPT.items()):
        _safe_print(f"  - {_name}: {_why}")

    _safe_print(f"HYG008 exempt (engine ladder does not apply) — {len(_HYG008_REMOTE_HOST)}:")
    for _name, _why in sorted(_HYG008_REMOTE_HOST.items()):
        _safe_print(f"  - {_name}: {_why}")

    if len(hyg8) <= _HYG008_PIN:
        _safe_print(
            f"HYG008 baseline: {len(hyg8)} docker-only checker(s) of the engine-touching "
            f"set — pin {_HYG008_PIN}, must shrink, never grow"
        )
        if len(hyg8) < _HYG008_PIN:
            _safe_print(f"  ratchet: lower _HYG008_PIN to {len(hyg8)} in this commit")

    # Printed on EVERY run, pass or fail. The whole defect this rule names is that the
    # scope of the gate was written down nowhere, so it drifted from "a subset" to "almost
    # everything" without anyone deciding that. A number nobody sees drifts again.
    if hyg10 is None:
        _safe_print("HYG010 NOT VERIFIED — could not enumerate Veil tests or workflows")
    else:
        _ungated, _total = hyg10[1], hyg10[2]
        _safe_print(
            f"HYG010 baseline: {_ungated} of {_total} jest test file(s) are run by no "
            f"gating CI invocation — pin {HYG010_UNGATED_PIN}, must shrink, never grow"
        )
        if _ungated < HYG010_UNGATED_PIN:
            _safe_print(f"  ratchet: lower HYG010_UNGATED_PIN to {_ungated} in this commit")

    _safe_print(
        f"HYG009 baseline: {len(hyg9)} documented-or-wired checker(s) git is NOT tracking "
        f"— pin {HYG009_PIN}, must shrink, never grow. A wired gate that is not committed "
        f"resolves to nothing in every clone and every CI run:"
    )
    for _n in hyg9:
        _safe_print(f"  [untracked] {_n}")
    if len(hyg9) > HYG009_PIN:
        findings = True
        _safe_print(
            f"HYG009: {len(hyg9)} untracked live checker(s) exceeds the pin of "
            f"{HYG009_PIN} — fix is a commit, not an allowlist entry"
        )
    elif len(hyg9) < HYG009_PIN:
        findings = True
        _safe_print(
            f"HYG009: pin is stale — {len(hyg9)} untracked, pin says {HYG009_PIN}. "
            f"Lower HYG009_PIN in the same commit that fixed them, or the win is given back."
        )

    known4 = [x for x in hyg4 if x.split(":")[0] in _HYG004_BASELINE]
    if known4:
        _safe_print(
            f"HYG004 baseline: {len(known4)} known parse-swallowing site(s) in "
            f"{len(_HYG004_BASELINE)} file(s) — must shrink, never grow:"
        )
        for n in known4:
            _safe_print(f"  [known] {n}")

    if _HYG004_EXEMPT_SITES:
        # Printed unconditionally, like every other exemption in this file: a rule that
        # quietly stopped counting things looks exactly like a rule with nothing to find.
        _safe_print(
            f"HYG004 exempt (None is a DEAD sentinel, caller exits 2) — "
            f"{len(_HYG004_EXEMPT_SITES)}:"
        )
        for n in _HYG004_EXEMPT_SITES:
            _safe_print(f"  {n}")

    if show_all or not findings:
        r = report
        _safe_print(f"tree: {r['total_checkers']} check_*.py | "
                    f"{len(r['no_selftest_tree'])} without --self-test | "
                    f"{len(r['wired_nowhere'])} wired nowhere | "
                    f"{len(r['wired_but_undocumented'])} wired-but-undocumented")
        if show_all:
            for n in r["wired_but_undocumented"]:
                _safe_print(f"  [report] wired but not documented: {n}")
            for n in r["no_selftest_tree"]:
                _safe_print(f"  [report] no --self-test (tree-wide): {n}")
            for n in r["wired_nowhere"]:
                _safe_print(f"  [report] wired nowhere (not in rules/CI/routines): {n}")

    if findings:
        # Count EVERY class that can set `findings`, not a subset. This used to
        # be hyg1+hyg2+hyg3+hyg5 while hyg6/hyg7/hyg8 and both HYG009 branches
        # could each set the flag on their own — so a run whose only problem was
        # HYG008 over its pin printed the self-contradicting
        #     HYGIENE: FAIL (0 violation(s))
        # and exited 1. A gate that reports a failure it cannot name is read as
        # broken and then ignored, which costs more than the defect it found.
        n_viol = (len(hyg1) + len(hyg2) + len(hyg3) + len(hyg5)
                  + len(hyg6) + len(hyg7)
                  + (len(hyg8) if len(hyg8) > _HYG008_PIN else 0)
                  + (1 if len(hyg9) != HYG009_PIN else 0)
                  # HYG010 and HYG013 each set `findings` on their own and were
                  # missing here, which is the same self-contradiction the note
                  # above records -- HYG010 by omission since it was added,
                  # HYG013 when it landed.
                  + (len(hyg10[0]) if hyg10 and hyg10[0] else 0)
                  + (1 if hyg13 is None
                     else (len(hyg13) if len(hyg13) > HYG013_PIN else 0))
                  + (1 if hyg14 is None
                     else (len(hyg14) if len(hyg14) > HYG014_PIN else 0)))
        _safe_print(f"HYGIENE: FAIL ({n_viol} violation(s))")
        return 1
    _safe_print("HYGIENE: ok")
    return 0


def _self_test_hyg10() -> list[str]:
    """Prove HYG010 can fail, and that its parser does not mis-read a scope into a pass.

    Both directions matter and the second is the one that bit: the first version of the
    rule read a POSITIONAL `npx jest src/x.test.ts` as "no pattern, so the whole suite is
    gated" and reported a clean 0 while 148 files went ungated.
    """
    bad: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Built from LAYOUT, never spelled literally. This fixture is the LAST
        # monorepo path in a file whose PORTABLE TWIN publishes to a public repo,
        # and the boundary scan is a BLOCKING gate: while it is red the sync
        # workflow publishes NOTHING at all. The indirection this uses already
        # existed for the rule itself (LAYOUT["jest_app"], line ~796) — only the
        # fixture was never migrated to it.
        veil = (root / (LAYOUT.get("jest_app") or "app")
                / "src/components/os/__tests__")
        veil.mkdir(parents=True)
        (veil / "a.test.tsx").write_text("test('a',()=>{})", encoding="utf-8")
        (veil / "b.test.tsx").write_text("test('b',()=>{})", encoding="utf-8")
        wf = root / ".github/workflows"
        wf.mkdir(parents=True)

        def write(body: str) -> None:
            (wf / "ci.yml").write_text(body, encoding="utf-8")

        # 1. A gating run scoped by a POSITIONAL path must NOT read as gating everything.
        write(
            "jobs:\n  j:\n    steps:\n"
            "      - run: npx jest src/components/os/__tests__/a.test.tsx\n"
        )
        r = _hyg10(root)
        if r is None or r[1] != 1:
            bad.append(f"HYG010 positional-path scope mis-parsed (ungated={r and r[1]}, want 1)")

        # 2. A run with NO scope at all really does gate everything.
        write("jobs:\n  j:\n    steps:\n      - run: npm test -- --ci\n")
        r = _hyg10(root)
        if r is None or r[1] != 0:
            bad.append(f"HYG010 unscoped run should gate all (ungated={r and r[1]}, want 0)")

        # 3. continue-on-error means the step is NOT a gate.
        write(
            "jobs:\n  j:\n    steps:\n"
            "      - continue-on-error: true\n        run: npm test -- --ci\n"
        )
        r = _hyg10(root)
        if r is None or r[1] != 2:
            bad.append(f"HYG010 tolerated failure counted as a gate (ungated={r and r[1]}, want 2)")

        # 4. No jest invocation anywhere => cannot judge, never a pass.
        write("jobs:\n  j:\n    steps:\n      - run: echo hi\n")
        if _hyg10(root) is not None:
            bad.append("HYG010 returned a verdict with no jest invocation to read")
    return bad


def _self_test_hyg11() -> list[str]:
    """Prove HYG011 fires on an untracked checker and NOT on a tracked one.

    A real git repo, because the rule asks git. Mocking that away would test
    the mock -- and the whole defect is that every non-git signal (the file is
    on disk, it imports, it self-tests) says the checker is fine.
    """
    out: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "tools"
        tree.mkdir(parents=True)
        for a in (["init", "-q"], ["config", "user.email", "t@t.t"],
                  ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", str(tree), *a], capture_output=True)
        (tree / "check_tracked.py").write_text("# tracked\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(tree), "add", "check_tracked.py"],
                       capture_output=True)
        subprocess.run(["git", "-C", str(tree), "commit", "-qm", "x"],
                       capture_output=True)

        clean = _hyg11([tree])
        if clean:
            out.append(f"HYG011 cried wolf on a tracked checker: {clean}")

        (tree / "check_untracked.py").write_text("# untracked\n", encoding="utf-8")
        caught = _hyg11([tree])
        if not any("check_untracked.py" in f for f in caught):
            out.append("HYG011 did NOT fire on an untracked checker")
        if any("check_tracked.py" in f for f in caught):
            out.append("HYG011 flagged the tracked checker too")
    return out


def self_test() -> int:
    """Prove the gate can still fail: feed it a rules file naming a checker
    that does not exist and assert HYG002 fires and the exit code is 1."""
    saved_rules_doc = LAYOUT["rules_doc"]
    LAYOUT["rules_doc"] = _SELFTEST_RULES_REL
    try:
        return _self_test_body()
    finally:
        LAYOUT["rules_doc"] = saved_rules_doc


_NL15 = chr(10)


def _self_test_body() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / _SELFTEST_RULES_REL).parent.mkdir(parents=True)
        (root / "dev/tools").mkdir(parents=True)
        (root / ".github/workflows").mkdir(parents=True)
        (root / _SELFTEST_RULES_REL).write_text(
            "run python dev/tools/check_nonexistent_thing_xyz.py\n",
            encoding="utf-8",
        )
        (root / ".github/workflows/debt-invariants.yml").write_text(
            "name: debt\non: {pull_request: {branches: [develop]}}\n"
            "jobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - run: python dev/tools/check_other_missing_abc.py\n",
            encoding="utf-8",
        )
        # A real checker with no self-test, so HYG001 can also fire.
        (root / "dev/tools/check_real_but_no_selftest.py").write_text(
            '"""a gate without a self-test"""\nimport sys\nsys.exit(0)\n',
            encoding="utf-8",
        )
        (root / _SELFTEST_RULES_REL).write_text(
            "run python dev/tools/check_nonexistent_thing_xyz.py\n"
            "run python dev/tools/check_real_but_no_selftest.py\n",
            encoding="utf-8",
        )
        # A drifted copy across delivery homes, so the parity rule can also fire. The pair
        # is taken from PARITY (data) rather than written as literals: this module
        # ships publicly and must name no repo's private layout. With no parity
        # registry — the portable copy — there is nothing for it to assert, and
        # the fixture is skipped rather than faked.
        if PARITY:
            canon_rel, copy_rel = PARITY[0]
            for rel, body in ((canon_rel, "canonical\n"), (copy_rel, "DRIFTED\n")):
                dest = root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(body, encoding="utf-8")
        # HYG004: a swallowing handler must fire; a subscript-recording one must not.
        (root / "dev/tools/check_swallows_parse.py").write_text(
            '"""x"""\nimport ast\n\n\ndef scan(p):\n'
            "    try:\n        return ast.parse(p)\n"
            "    except SyntaxError:\n        return None\n\n\n"
            'def self_test():\n    return 0\n',
            encoding="utf-8",
        )
        (root / "dev/tools/check_records_parse.py").write_text(
            '"""x"""\nimport ast\nBAD = {}\n\n\ndef scan(p):\n'
            "    try:\n        return ast.parse(p)\n"
            "    except SyntaxError as exc:\n"
            "        BAD[p] = type(exc).__name__\n        return None\n\n\n"
            'def self_test():\n    return 0\n',
            encoding="utf-8",
        )
        # HYG004 exemption: `return None` is NOT a swallow when a caller reads None as
        # "could not judge" and exits 2 — the sentinel idiom this rule's own docstring
        # recommends. Both directions are asserted: the contract earns the exemption,
        # and an identical handler WITHOUT it must still fire, or the exemption is a
        # hole rather than a refinement.
        (root / "dev/tools/check_sentinel_parse.py").write_text(
            '"""x"""\nimport ast\nimport sys\n\n\ndef scan(p):\n'
            "    try:\n        return ast.parse(p)\n"
            "    except SyntaxError:\n        return None\n\n\n"
            "def main():\n    bad = scan('x')\n    if bad is None:\n"
            '        print("NOT VERIFIED")\n        return 2\n    return 0\n\n\n'
            'def self_test():\n    return 0\n',
            encoding="utf-8",
        )
        # HYG012: a module that says one name twice, and its near-miss twin. The
        # SECOND file is the half that matters — a def nested inside `if`/`try` is
        # the conditional-fallback idiom used all over this tree, and a rule that
        # flags it floods and gets switched off rather than satisfied.
        (root / "dev/tools/check_shadowed_rule.py").write_text(
            '"""x"""\n\n\ndef check_thing(src):\n    return []\n\n\n'
            "def check_thing():\n    return []\n\n\n"
            'def self_test():\n    return 0\n',
            encoding="utf-8",
        )
        (root / "dev/tools/check_conditional_def.py").write_text(
            '"""x"""\n\ntry:\n    import tomllib\n\n    def load(p):\n        return 1\n'
            "except ModuleNotFoundError:\n\n    def load(p):\n        return 2\n\n\n"
            'def self_test():\n    return 0\n',
            encoding="utf-8",
        )
        (hyg1, hyg2, hyg3, hyg4, hyg5, hyg6, _hyg7, _hyg8, hyg9, _hyg10,
         hyg13, _hyg14_unused, _hyg15_unused, _) = _collect(root)
        if not any("check_shadowed_rule" in x and "HYG012" in x for x in hyg3):
            print("SELF-TEST FAIL: HYG012 did not fire on a module defining "
                  "`check_thing` twice at module level — the later def shadows the "
                  "earlier one and a signature mismatch kills the whole checker",
                  file=sys.stderr)
            return 1
        if any("check_conditional_def" in x for x in hyg3):
            print("SELF-TEST FAIL: HYG012 cried wolf on a try/except fallback def — "
                  "that is the guarded-import idiom, not a shadowed rule",
                  file=sys.stderr)
            return 1
        _safe_print("  HYG012: ok - fires on a shadowed module-level def, silent on a "
                    "try/except fallback")

        # HYG013: an untracked agent-context file must be NAMED, a tracked one
        # must not be. Only the pair is evidence -- a rule that fires on
        # everything passes the first half and is noise.
        #
        # Its OWN git repo: the shared self-test root is a plain tempdir, so
        # _hyg13 correctly answers None there (fail-closed) and neither arm
        # could be exercised.
        with tempfile.TemporaryDirectory() as _t13:
            _r13 = Path(_t13)
            (_r13 / ".config").mkdir(parents=True)
            (_r13 / ".config/tracked.md").write_text("t", encoding="utf-8")
            (_r13 / ".config/untracked.md").write_text("u", encoding="utf-8")
            for _cmd in (["git", "init", "-q"],
                         ["git", "add", ".config/tracked.md"]):
                subprocess.run(_cmd, cwd=_r13, capture_output=True, check=False)
            _h13 = _hyg13(_r13)
            if _h13 is None:
                print("SELF-TEST FAIL: HYG013 could not ask git in a real repo",
                      file=sys.stderr)
                return 1
            if not any("untracked.md" in x for x in _h13):
                print("SELF-TEST FAIL: HYG013 did not name an UNTRACKED "
                      "agent-context file -- a rule loaded on this machine and "
                      "absent from every clone is the whole defect", file=sys.stderr)
                return 1
            if any("tracked.md" in x and "untracked.md" not in x for x in _h13):
                print("SELF-TEST FAIL: HYG013 flagged a TRACKED file -- a rule "
                      "that fires on everything gets switched off rather than "
                      "satisfied", file=sys.stderr)
                return 1
        # -- HYG015 -------------------------------------------------------
        # The real defect (lambda_box.py, 2026-08-23) and the THREE false
        # positives that the first version produced. Only the pair is evidence:
        # a rule that fires on every self-test would have sent someone to
        # "fix" three healthy checkers.
        with tempfile.TemporaryDirectory() as _t15:
            _r15 = Path(_t15)
            _d15 = _r15 / "AitherOS" / "dev" / "tools"
            _d15.mkdir(parents=True)
            _hdr = ("def self_test():" + _NL15 +
                    "    bad = 0" + _NL15 +
                    "    def ck(c, w):" + _NL15 +
                    "        nonlocal bad" + _NL15 +
                    "        if not c:" + _NL15 +
                    "            bad += 1" + _NL15 +
                    "    ck(True, 'first')" + _NL15)
            # BAD: the counter verdict sits mid-function; later arms are orphaned.
            (_d15 / "bad_tool.py").write_text(
                _hdr +
                "    if bad:" + _NL15 +
                "        return 1" + _NL15 +
                "    ck(True, 'stranded')" + _NL15 +
                "    print('PASSED')" + _NL15 +
                "    return 0" + _NL15, encoding="utf-8")
            # GOOD: verdict last.
            (_d15 / "good_tool.py").write_text(
                _hdr +
                "    ck(True, 'second')" + _NL15 +
                "    if bad:" + _NL15 +
                "        return 1" + _NL15 +
                "    return 0" + _NL15, encoding="utf-8")
            # FALSE-POSITIVE 1: an EXCEPT-handler abort is a DEAD exit, not a
            # verdict -- the arms after it do not run when it fires.
            (_d15 / "abort_tool.py").write_text(
                _hdr +
                "    try:" + _NL15 +
                "        load()" + _NL15 +
                "    except OSError:" + _NL15 +
                "        return 1" + _NL15 +
                "    ck(True, 'after an abort is fine')" + _NL15 +
                "    if bad:" + _NL15 +
                "        return 1" + _NL15 +
                "    return 0" + _NL15, encoding="utf-8")
            # FALSE-POSITIVE 2: `return True` == 1 in Python (bool is an int).
            (_d15 / "bool_tool.py").write_text(
                _hdr +
                "    def pred():" + _NL15 +
                "        return True" + _NL15 +
                "    ck(pred(), 'a nested predicate is not a verdict')" + _NL15 +
                "    if bad:" + _NL15 +
                "        return 1" + _NL15 +
                "    return 0" + _NL15, encoding="utf-8")
            _h15 = _hyg015(_r15)
            if _h15 is None:
                print("SELF-TEST FAIL: HYG015 could not read its own fixture "
                      "tree -- None is DEAD, and a rule that cannot look must "
                      "never read as clean", file=sys.stderr)
                return 1
            if not any("bad_tool.py" in x for x in _h15):
                print("SELF-TEST FAIL: HYG015 missed a verdict returning "
                      "MID-FUNCTION with assertions stranded after it -- the "
                      "exact lambda_box.py shape it was written for",
                      file=sys.stderr)
                return 1
            for _n15, _why15 in (
                    ("good_tool.py", "a verdict at the END is correct"),
                    ("abort_tool.py", "an except-handler abort is a DEAD exit, "
                                      "not a counter verdict"),
                    ("bool_tool.py", "`return True` equals 1 in Python; a "
                                     "nested predicate is not a verdict")):
                if any(_n15 in x for x in _h15):
                    print("SELF-TEST FAIL: HYG015 cried wolf on %s -- %s. A "
                          "rule that floods gets switched off rather than "
                          "satisfied." % (_n15, _why15), file=sys.stderr)
                    return 1
            _safe_print("  HYG015: ok - fires on a stranded arm, silent on a "
                        "correct verdict, an except-abort and a bool return")

        # ── HYG014 ──────────────────────────────────────────────────────────
        # The defect: shell the engine, test the return code, hand back an empty
        # collection. Downstream that is indistinguishable from a real zero, and
        # for a gate the two mean opposite things.
        with tempfile.TemporaryDirectory() as _t14:
            _r14 = Path(_t14)
            _d14 = _r14 / "AitherOS" / "dev" / "tools"
            _d14.mkdir(parents=True)
            (_d14 / "bad_probe.py").write_text(
                "import subprocess\n"
                "def list_them(engine):\n"
                "    p = subprocess.run(['podman', 'ps', '-q'])\n"
                "    if p.returncode != 0:\n"
                "        return []\n"
                "    return p.stdout.splitlines()\n",
                encoding="utf-8")
            # The two real fixes, which must stay SILENT or every repaired call
            # site would be flagged and the rule would be switched off.
            (_d14 / "good_none.py").write_text(
                "import subprocess\n"
                "def list_them(engine):\n"
                "    p = subprocess.run(['podman', 'ps', '-q'])\n"
                "    if p.returncode != 0:\n"
                "        return None\n"
                "    return p.stdout.splitlines()\n",
                encoding="utf-8")
            (_d14 / "good_raise.py").write_text(
                "import subprocess\n"
                "def list_them(engine):\n"
                "    p = subprocess.run(['podman', 'ps', '-q'])\n"
                "    if p.returncode != 0:\n"
                "        raise RuntimeError('could not enumerate')\n"
                "    return p.stdout.splitlines()\n",
                encoding="utf-8")
            # No engine anywhere: an ordinary empty return is not this defect.
            (_d14 / "unrelated.py").write_text(
                "def parse(text):\n"
                "    rc = 1\n"
                "    if rc != 0:\n"
                "        return []\n"
                "    return [text]\n",
                encoding="utf-8")

            _h14 = _hyg14(_r14)
            if _h14 is None:
                print("SELF-TEST FAIL: HYG014 could not read a tree it just built",
                      file=sys.stderr)
                return 1
            if not any("bad_probe.py" in x for x in _h14):
                print("SELF-TEST FAIL: HYG014 did not flag an engine probe "
                      "returning [] on failure -- the whole defect", file=sys.stderr)
                return 1
            for _quiet in ("good_none.py", "good_raise.py", "unrelated.py"):
                if any(_quiet in x for x in _h14):
                    print(f"SELF-TEST FAIL: HYG014 flagged {_quiet} -- returning "
                          "None, raising, and non-engine code are the FIXES and "
                          "the out-of-scope case; a rule that fires on those gets "
                          "switched off rather than satisfied", file=sys.stderr)
                    return 1

        # A walk that read nothing must answer None, never [] -- otherwise this
        # rule is an instance of the very defect it checks for.
        with tempfile.TemporaryDirectory() as _t14b:
            if _hyg14(Path(_t14b)) is not None:
                print("SELF-TEST FAIL: HYG014 returned a verdict for a tree with "
                      "no sources -- 'I could not look' reported as 'nothing wrong'",
                      file=sys.stderr)
                return 1

        # Fail CLOSED: a tree git cannot answer for yields None, never [].
        with tempfile.TemporaryDirectory() as _t13b:
            _r13b = Path(_t13b)
            (_r13b / ".config").mkdir(parents=True)
            (_r13b / ".config/x.md").write_text("x", encoding="utf-8")
            if _hyg13(_r13b) is not None:
                print("SELF-TEST FAIL: HYG013 answered for a NON-GIT tree instead "
                      "of reporting it could not judge -- [] there would read as "
                      "'everything is tracked'", file=sys.stderr)
                return 1
        _safe_print("  HYG013: ok - names an untracked agent-context file, silent on a "
                    "tracked one, and DEAD rather than clean off-git")

        # HYG006: fires on the real shape, and is silent on BOTH ways of being
        # correct. It had NO self-test arm at all until 2026-08-22, which is how
        # its false positive shipped: the mention test read RAW source, so a file
        # that merely NAMES the marker in a `#` comment became a candidate -- and
        # a file that never reads the marker has no comment-skipping idiom
        # either, so it was then reported as parsing it wrongly.
        # `run_fleet_gates_from_host.py` was flagged for a one-line comment.
        # Only the pair-of-silences is evidence: a rule that fires on everything
        # passes the "does it fire?" arm and is noise.
        _nl6, _q6 = chr(10), chr(34)
        with tempfile.TemporaryDirectory() as _t6:
            _r6 = Path(_t6)
            (_r6 / "check_whole_read.py").write_text(
                '"""x"""' + _nl6 + _nl6
                + "def root(p):" + _nl6
                + "    return open(p / " + _q6
                + ".canonical-deploy-root" + _q6
                + ").read().strip()" + _nl6,
                encoding="utf-8")
            (_r6 / "check_linewise.py").write_text(
                '"""x"""' + _nl6 + _nl6
                + "def root(p):" + _nl6
                + "    for line in open(p / " + _q6 + ".canonical-deploy-root" + _q6 + "):" + _nl6
                + "        if line.startswith(" + _q6 + "#" + _q6 + "):" + _nl6
                + "            continue" + _nl6
                + "        return line.strip()" + _nl6,
                encoding="utf-8")
            (_r6 / "check_only_mentions.py").write_text(
                '"""x"""' + _nl6 + _nl6
                + "# HOST_ONLY: this gate needs the .canonical-deploy-root tree, not a" + _nl6
                + "# worktree -- see the module docstring. It does not read the marker." + _nl6
                + "def run():" + _nl6
                + "    return []" + _nl6,
                encoding="utf-8")
            _h6 = _marker_parse_violations(_r6)
            if not any("check_whole_read" in x for x in _h6):
                print("SELF-TEST FAIL: HYG006 did not fire on a tool reading the "
                      "deploy-root marker WHOLE -- the comment lines make the string "
                      "a non-directory, so the tool falls back to the working tree "
                      "and silently answers about the wrong tree", file=sys.stderr)
                return 1
            if any("check_linewise" in x for x in _h6):
                print("SELF-TEST FAIL: HYG006 cried wolf on a tool that skips comment "
                      "lines correctly", file=sys.stderr)
                return 1
            if any("check_only_mentions" in x for x in _h6):
                print("SELF-TEST FAIL: HYG006 flagged a file that only NAMES the "
                      "marker in a comment and never reads it -- flagging the "
                      "documentation of a defect as the defect is how a gate gets "
                      "deleted rather than satisfied", file=sys.stderr)
                return 1
        _safe_print("  HYG006: ok - fires on a whole-file read, silent on a line-wise "
                    "parser and on a comment-only mention")
        if any("check_sentinel_parse" in x for x in hyg4):
            print("SELF-TEST FAIL: HYG004 fired on a None SENTINEL whose caller tests "
                  "`is None` and exits 2 — that is the correct idiom, not a swallow",
                  file=sys.stderr)
            return 1
        if not any("check_sentinel_parse" in x for x in _HYG004_EXEMPT_SITES):
            print("SELF-TEST FAIL: the HYG004 exemption did not RECORD the site it "
                  "excused; an invisible exemption is indistinguishable from a rule "
                  "that stopped firing", file=sys.stderr)
            return 1
        if not any("check_swallows_parse" in x for x in hyg4):
            print("SELF-TEST FAIL: HYG004 did not fire on a swallowing handler",
                  file=sys.stderr)
            return 1
        if any("check_records_parse" in x for x in hyg4):
            print("SELF-TEST FAIL: HYG004 fired on a handler that RECORDS the failure",
                  file=sys.stderr)
            return 1
        if not hyg1 or not hyg2 or not hyg3:
            print(
                "SELF-TEST FAIL: expected HYG001/HYG002/HYG003 to "
                f"fire, got {hyg1!r} {hyg2!r} {hyg3!r}",
                file=sys.stderr,
            )
            return 1
        # HYG005 asserts parity across delivery homes, which only exists where a
        # parity registry does. In the PORTABLE copy there is none, so the rule is
        # NOT APPLICABLE — reported, never silently treated as "parity holds".
        # Demanding it fire there would make the twin's self-test permanently red
        # and teach the next person to ignore it.
        if PARITY:
            if not hyg5:
                print(
                    f"SELF-TEST FAIL: expected HYG005 to fire, got {hyg5!r}",
                    file=sys.stderr,
                )
                return 1
        else:
            print("  HYG005: NOT APPLICABLE — no parity registry in this copy")
        code = run(root, show_all=False)
        if code != 1:
            print(f"SELF-TEST FAIL: expected exit 1, got {code}", file=sys.stderr)
            return 1
    hyg10_bad = _self_test_hyg10()
    if hyg10_bad:
        for line in hyg10_bad:
            print(f"SELF-TEST FAIL: {line}", file=sys.stderr)
        return 1
    _safe_print("  HYG010: ok - scope parsing, tolerated steps, and no-verdict all correct")
    hyg11_bad = _self_test_hyg11()
    if hyg11_bad:
        for line in hyg11_bad:
            print(f"SELF-TEST FAIL: {line}", file=sys.stderr)
        return 1
    _safe_print("  HYG011: ok - fires on an untracked checker, silent on a tracked one")
    _safe_print("SELF-TEST: ok - the gate can still fail")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true",
                    help="prove the gate can still fail")
    ap.add_argument("--all", action="store_true",
                    help="print the full tree backlog (report, never a gate)")
    ap.add_argument("--root", default=None,
                    help="repo root (default: git rev-parse from cwd)")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    root = Path(args.root).resolve() if args.root else find_root(Path.cwd())
    return run(root, show_all=args.all)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # a probe that cannot judge is never a pass
        print(f"CANNOT RUN: {exc}", file=sys.stderr)
        sys.exit(2)
