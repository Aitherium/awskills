#!/usr/bin/env python3
"""PF001 - is this tool call bypassing a platform lane RIGHT NOW?

THE RULE (owner, 2026-11-18, the fifth time): never hand-roll anything. Almost
everything should be using the platform, and when the platform has no
agent/tool/skill/package/service/feature for the job, BUILDING THAT is priority
one, before the job runs. Find and extend; never rebuild. Never hand-roll a
script or start a bare process.

Memory and prose did not stop it, so this is enforcement. Seven deny rules, each
written from a command that actually ran on 2026-11-18 - not from a guess:

  D1  a detached launcher (Start-Process / cmd `start` / wslg) running an
      interpreter or a script          -> awrun, awsh_awrun_queue, film_render,
                                          mcp__aitheros__desktop_open
  D2  a raw fleet shell (wsl + nsenter / sh /mnt/c/..., systemctl unit writes,
      podman exec of a host script)    -> mcp__aitheros__fleet_control + the
                                          documented fleet-deploy op
  D3  generated code (heredoc, python -c, pwsh -Command) that WRITES a script or
      data file outside any git work tree                      -> awgit wt new
  D4  ffmpeg/sox doing a deliverable concat or a/v mux          -> mediaforge_run_op
                                          film_assemble / mux_audio / film_render
  D5  gh release / npm publish / docker push in a repo that declares no release
      lane                                                    -> the declared
                                          release workflow, or awrel
  D6  hand-rolled orchestration (until/while + sleep, nohup, disown, detached &)
                                                                -> awsh_awrun_queue,
                                          tasks_job_schedule, a routine yaml
  D7  killing a lock/lease directory or a platform daemon by hand
                                                                -> awgit lease release,
                                          the owning platform CLI / aw_ops.py

WHAT IS ALLOWED WITHOUT A BYPASS: every read-only probe, git/gh inside a
worktree, the platform CLIs themselves, the repo's own gates, loopback health
probes, ffprobe and `ffmpeg -i in -f null -`, and a heredoc that only reads and
prints. ALLOW_PREFIXES / ALLOW_REGEX are checked FIRST and are asserted by
--self-test, so over-blocking is a test failure, not a surprise.

TWO ESCAPE HATCHES, both visible:
  AW_PLATFORM_FIRST_OK=1 <cmd>   allow this one command and append a row
                                (timestamp, session, rule id, sha256, the
                                program + first argument - never the whole
                                command, it may hold a secret) to
                                ~/.aither/platform_first/.
  AW_PLATFORM_FIRST_OFF=1        disable the guard and say so on stderr.

FAIL OPEN, ALWAYS. An unknown tool, a malformed payload or any exception is an
ALLOW: a crashed guard must never wedge a tool call (the awgit deploy-tree
precedent - advice with teeth, not a crash).

WHERE THIS FILE LIVES. This is the single editable source. gen_platform_first.py
renders it BYTE-IDENTICALLY into awsettings/awsettings/platform_first.py (the
console script `awsettings-guard`, distributed to every machine by awsettings'
portable hooks) and awskills/hooks/pre_bash_platform_first.py (the twin a
stranger's repo can copy-paste). LAW 15: generate, never copy by hand; the
checker-hygiene parity rule asserts the three stay identical, and this text names
no rule id of its own because the published copy must not carry one.

    python platform_first_rules.py --self-test
    python platform_first_rules.py --list-rules
    python platform_first_rules.py --metrics
    echo '<PreToolUse json>' | awsettings-guard            # JSON deny contract
    python pre_bash_platform_first.py --exit2              # exit 2 + stderr

Exit: 0 allow, 2 deny (exit-2 mode only). Never any other code.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#: Bumped when the rule set changes shape; the reasoning-doctrine block and the
#: gate both name it, so a stale copy is identifiable in a log.
VERSION = "1"

RULE_PREFIX = "PLATFORM FIRST"
BYPASS_ENV = "AW_PLATFORM_FIRST_OK"
OFF_ENV = "AW_PLATFORM_FIRST_OFF"
LOG_DIR_ENV = "AW_PLATFORM_FIRST_LOG_DIR"
MODE_ENV = "AW_PLATFORM_FIRST_MODE"
RELEASE_LANE_ENV = "AW_PLATFORM_FIRST_RELEASE_LANE"

#: The sentence every refusal ends with. The owner's "priority number 1".
PRIORITY_SENTENCE = (
    "if that lane does not exist or is broken, building/repairing it in its own repo is "
    "priority 1: file it on Atlas (tasks_create priority=1) and fix it before running this job."
)

GUARDED_TOOLS = ("Bash", "PowerShell")

# ---------------------------------------------------------------------------
# ALLOW TABLES - checked BEFORE any deny rule.
# ---------------------------------------------------------------------------

#: Read-only probes, the platform's own CLIs, and the repo's doc flow. Matched as
#: a token prefix: the step must equal the entry or continue with a space, so
#: "git status" never allows "git statusx" and "awgit" never allows "awgitx".
ALLOW_PREFIXES: Tuple[str, ...] = (
    # read-only probes
    "ls", "dir", "cat", "head", "tail", "grep", "rg", "find", "wc", "stat",
    "file", "jq", "which", "where", "whoami", "date", "env", "echo", "printf",
    "true", "test", "cd", "pwd", "basename", "dirname", "realpath", "readlink",
    "sed -n", "sort", "uniq", "cut", "tr", "diff", "cmp", "tree", "du", "df",
    "py --version", "python --version", "python3 --version", "node --version",
    # git / gh reads and the PR flow inside a worktree
    "git status", "git log", "git diff", "git show", "git branch", "git rev-parse",
    "git ls-files", "git ls-tree", "git blame", "git remote", "git tag",
    "git add", "git commit", "git push", "git fetch", "git checkout", "git switch",
    "git restore", "git worktree", "git stash list", "git config --get",
    "git config -l", "git check-ignore", "git merge-base", "git cat-file",
    "gh pr view", "gh pr list", "gh pr checks", "gh pr diff", "gh pr create",
    "gh pr merge", "gh pr comment", "gh pr ready", "gh pr edit", "gh pr status",
    "gh run view", "gh run list", "gh run watch", "gh issue view", "gh issue list",
    "gh workflow list", "gh workflow view", "gh release view", "gh release list",
    "gh api", "gh auth status", "gh repo view",
    # the platform's own lanes
    "awgit", "awrun", "awsettings", "awrelay", "awm", "awfind", "awkno", "aw_ops",
    "awsupervise", "awsh", "awfocus", "awask", "awbrowse", "awdesk", "awdk", "adk",
    "awcap", "awgraph", "awindex", "awprove", "awrtifact", "awexpress", "awflow",
    "awmine", "awgather", "awknowledge", "awcard", "awask-card", "awlease",
    # test runners and formatters: already automation
    "pytest", "ruff", "mypy", "black", "isort", "shellcheck", "actionlint",
    "python -m pytest", "python -m ruff", "python -m mypy", "python -m black",
    "python3 -m pytest", "python3 -m ruff", "python -m unittest",
    "node --test", "npx eslint", "npm test", "npm run",
)

#: Shapes a token prefix cannot express. Every one is asserted by --self-test.
ALLOW_REGEX: Tuple[re.Pattern, ...] = (
    # loopback health probe: GET only, no body, no upload
    re.compile(
        r"(?i)^curl\b"
        r"(?![^\n]*\s(?:-X|--request)\s+(?!GET\b)\w)"
        r"(?![^\n]*\s(?:-d|--data|-F|--form|-T|--upload-file)\b)"
        r"[^\n]*\bhttps?://(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?/"
    ),
    # dispatch Rung 2: read-only fleet health through the container itself
    re.compile(
        r"(?is)^wsl(?:\.exe)?\b(?![^\n]*(?:nsenter|/mnt/c/))[^\n]*\bpodman\s+exec\b"
        r"[^\n]*\bcurl\b[^\n]*https://localhost"
    ),
    # media PROBES
    re.compile(r"(?i)^ffprobe(?:\.exe)?\b"),
    re.compile(r"(?i)^ffmpeg(?:\.exe)?\b(?=[^\n]*(?:\s-f\s+null\b|--format\s+null))(?![^\n]*-f\s+concat)"),
    # the repo's own gates
    re.compile(
        r"(?i)^(?:python[0-9.]*|py|bash|pwsh|powershell)\b[^\n]*\b"
        r"(?:pr_local_verify|pr_local_review|run_gates|run_fleet_gates_from_host|check_[a-z0-9_]+)"
        r"\.py\b"
    ),
    re.compile(r"(?i)^(?:bash\s+)?[^\n]*\bsync-deploy-tree\.sh\b"),
    # a POSIX shebang bash step that is only a case-test prefilter is a no-op here
    re.compile(r"(?i)^(?:python[0-9.]*|py)\s+-S\s"),
)

# ---------------------------------------------------------------------------
# MASKING AND SPLITTING
# ---------------------------------------------------------------------------

_HEREDOC_HEAD = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")

#: Split a compound command into steps, never inside a quoted string.
#: COPIED VERBATIM (semantics, not text) from harvest_manual_toil._split_steps -
#: this module is rendered into packages that cannot import the monorepo, so the
#: function travels as a generated copy and gen_platform_first.py --self-test
#: asserts the two agree on a fixture set. A drift between them is a red gate.
_STEP_SPLIT = re.compile(r"\s*(?:&&|\|\||;|\n|\|)\s*")


def split_steps(command: str) -> List[str]:
    """Split a compound command on unquoted separators, keeping every argument."""
    masked = list(command)
    quote = ""
    i = 0
    while i < len(masked):
        ch = command[i]
        if quote:
            if ch == "\\" and quote == '"' and i + 1 < len(masked):
                masked[i] = masked[i + 1] = "_"
                i += 2
                continue
            if ch == quote:
                quote = ""
            masked[i] = "_"
        elif ch in "'\"":
            quote = ch
            masked[i] = "_"
        i += 1
    steps, start = [], 0
    for found in _STEP_SPLIT.finditer("".join(masked)):
        steps.append(command[start:found.start()])
        start = found.end()
    steps.append(command[start:])
    return [s for s in steps if s.strip()]


def _mask(command: str) -> str:
    """Quoted spans and heredoc BODIES become '_' - data, not a command.

    Same length as the input, so nothing downstream has to remap offsets. The
    heredoc BODY is masked because `cat <<'EOF' ... ffmpeg -f concat ... EOF`
    documents the bypass instead of committing it; the introducer stays readable
    so an interpreter heredoc is still recognisable.
    """
    out = list(command)
    i, n = 0, len(command)
    quote = ""
    while i < n:
        ch = command[i]
        if quote:
            if ch == "\\" and quote == '"' and i + 1 < n:
                out[i] = out[i + 1] = "_"
                i += 2
                continue
            if ch == quote:
                quote = ""
            out[i] = "_"
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            out[i] = "_"
            i += 1
            continue
        if command.startswith("<<", i) and not command.startswith("<<<", i):
            m = _HEREDOC_HEAD.match(command, i)
            if m and m.group(2):
                word = m.group(2)
                nl = command.find("\n", m.end())
                if nl < 0:
                    i = n
                    break
                j = nl + 1
                done = False
                while j < n:
                    le = command.find("\n", j)
                    line = command[j:le] if le >= 0 else command[j:]
                    if line.strip() == word:
                        for k in range(nl + 1, j):
                            if out[k] != "\n":
                                out[k] = "_"
                        i = (le + 1) if le >= 0 else n
                        done = True
                        break
                    if le < 0:
                        for k in range(nl + 1, n):
                            if out[k] != "\n":
                                out[k] = "_"
                        i = n
                        done = True
                        break
                    j = le + 1
                if done:
                    continue
        i += 1
    return "".join(out)


def heredoc_blocks(command: str) -> List[Tuple[str, str]]:
    """(head, body) for every heredoc. head is the line carrying ``<<WORD``."""
    out: List[Tuple[str, str]] = []
    i, n = 0, len(command)
    quote = ""
    while i < n:
        ch = command[i]
        if quote:
            if ch == "\\" and quote == '"' and i + 1 < n:
                i += 2
                continue
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            i += 1
            continue
        if command.startswith("<<", i) and not command.startswith("<<<", i):
            m = _HEREDOC_HEAD.match(command, i)
            if m and m.group(2):
                word = m.group(2)
                line_start = command.rfind("\n", 0, i) + 1
                head = command[line_start:i]
                nl = command.find("\n", m.end())
                if nl < 0:
                    return out
                j = nl + 1
                body_start = j
                while True:
                    le = command.find("\n", j)
                    line = command[j:le] if le >= 0 else command[j:]
                    if line.strip() == word:
                        out.append((head, command[body_start:j]))
                        i = (le + 1) if le >= 0 else n
                        break
                    if le < 0:
                        out.append((head, command[body_start:]))
                        return out
                    j = le + 1
                continue
        i += 1
    return out


_ASSIGNMENT = re.compile(
    r"""^(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|'[^']*'|\S*))\s+"""
)


def _strip_assignments(step: str) -> str:
    s = step.strip()
    while True:
        m = _ASSIGNMENT.match(s)
        if not m:
            return s
        s = s[m.end():]


def is_allowed(step: str) -> bool:
    """True when this step is one of the things the owner listed as legitimate."""
    s = _strip_assignments(step).strip()
    if not s:
        return True
    if s.lstrip().startswith("#"):
        return True
    low = s.lower()
    for p in ALLOW_PREFIXES:
        if low == p or low.startswith(p + " "):
            return True
    for rx in ALLOW_REGEX:
        if rx.match(s):
            return True
    return False


# ---------------------------------------------------------------------------
# FILESYSTEM HELPERS - only reached once a rule's cheap shape has matched.
# ---------------------------------------------------------------------------

_WT_CACHE: Dict[str, bool] = {}
_WARNED: set = set()


def _warn_once(key: str, message: str) -> None:
    """Say a thing once on stderr. A guard that fails soft must still be audible:
    a silent handler is how a failed lane becomes 'the feature is off'."""
    if key in _WARNED:
        return
    _WARNED.add(key)
    try:
        print(f"{RULE_PREFIX}: {message}", file=sys.stderr)
    except (OSError, ValueError):
        return


def _emit(stream: Any, text: str) -> bool:
    """Write to a hook's stderr/stdout, tolerating a closed stream."""
    try:
        print(text, file=stream)
        return True
    except (OSError, ValueError):
        return False


def _in_git_worktree(path: str, cwd: Optional[str]) -> bool:
    """Is ``path`` inside ANY git work tree? Cached per directory; no subprocess."""
    try:
        base = path if os.path.isabs(path) else os.path.join(cwd or os.getcwd(), path)
        parent = os.path.dirname(os.path.abspath(base))
    except (OSError, ValueError):
        return False
    key = parent.lower()
    if key in _WT_CACHE:
        return _WT_CACHE[key]
    hit = False
    cur = parent
    while True:
        try:
            if os.path.exists(os.path.join(cur, ".git")):
                hit = True
                break
        except OSError:
            break
        nxt = os.path.dirname(cur)
        if nxt == cur or not nxt:
            break
        cur = nxt
    _WT_CACHE[key] = hit
    return hit


_LANE_CACHE: Dict[str, bool] = {}


def _release_lane(cwd: Optional[str], env: Dict[str, str]) -> bool:
    """Does the repo at ``cwd`` declare a release lane? Workflow file or ecosystem.yaml."""
    if env.get(RELEASE_LANE_ENV, "").strip() in ("1", "true", "yes"):
        return True
    root = os.path.abspath(cwd or os.getcwd())
    key = root.lower()
    if key in _LANE_CACHE:
        return _LANE_CACHE[key]
    declared = False
    cur = root
    while True:
        gf = os.path.join(cur, ".github", "workflows")
        if os.path.isdir(gf):
            try:
                for name in os.listdir(gf):
                    if name.lower().endswith((".yml", ".yaml")) and "release" in name.lower():
                        declared = True
                        break
            except OSError as exc:
                _warn_once("release-lane-listdir",
                           f"could not read {gf} ({exc}); treating the release lane as absent")
            break
        nxt = os.path.dirname(cur)
        if nxt == cur or not nxt:
            break
        cur = nxt
    if not declared:
        for cand in (os.path.join(root, "AitherOS", "config", "ecosystem.yaml"),
                     os.path.join(root, "config", "ecosystem.yaml"),
                     os.path.join(root, "ecosystem.yaml")):
            try:
                text = Path(cand).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            idx = text.find("release_lanes:")
            if idx >= 0:
                declared = True
            break
    _LANE_CACHE[key] = declared
    return declared


# ---------------------------------------------------------------------------
# DENY RULES
# ---------------------------------------------------------------------------

_INTERP = re.compile(
    r"(?i)\b(?:python[0-9.]*|py|pwsh|powershell|bash|sh|zsh|node|perl|ruby)\b"
)
_INTERP_POS = re.compile(
    r"(?i)^(?:python[0-9.]*|py|pwsh|powershell|bash|sh|zsh|node|perl|ruby)\b"
)

# D1 - a detached launcher running an interpreter or a script.
_D1_LAUNCH = re.compile(
    r"(?i)(?:^|[;&|(])\s*(?:Start-Process|start(?:\.exe)?|wslg(?:\.exe)?)\b"
)
_D1_TARGET = re.compile(
    r"(?i)\b(?:bash|sh|zsh|pwsh|powershell|cmd|python[0-9.]*|py|node|wslg)(?:\.exe)?\b"
    r"|\.(?:sh|ps1|py|cmd|bat)\b"
)

# D2 - a raw fleet shell.
_D2 = re.compile(
    r"""(?xi)
      \bnsenter\b
    | \bwsl(?:\.exe)?\b[^\n]*?(?:--\s*)?
        (?:\bsh\s+/mnt/c/|\bbash\s+/mnt/c/|/mnt/c/[^\s]*\.(?:sh|py|ps1|cmd))
    | \bsystemctl\b[^\n]*?\b(?:edit|link|mask)\b
    | >\s*/etc/systemd/system/
    | \bpodman\s+(?:exec|run)\b[^\n]*?/mnt/c/
    | \bpodman\s+cp\b
    | \bdocker\s+exec\b[^\n]*?/mnt/c/
    """
)

# D3 - generated code that writes outside a work tree.
_D3_WRITE = re.compile(
    r"""(?xi)
      open\s*\(\s*[^,()\n]{0,200}?,\s*(?:mode\s*=\s*)?['"][rbtu]*[wax+]
    | \.write_text\s*\( | \.write_bytes\s*\( | \bwritelines\s*\(
    | \bjson\.dump\s*\( | \b(?:yaml|toml)\.(?:safe_)?dump\s*\(
    | \b(?:Set-Content|Add-Content|Out-File)\b
    | \bshutil\.(?:copy|copyfile|move)\w*\s*\(
    | >\s*[^\s;|&<>]+\.(?:py|sh|ps1|cmd|bat|json|ya?ml)\b
    """
)
_D3_TARGETS_RE = re.compile(
    r"""(?xi)
      ['"]([^'"\n]{1,300}?\.(?:py|sh|ps1|cmd|bat|json|ya?ml))['"]
    | >\s*([^\s;|&<>]+\.(?:py|sh|ps1|cmd|bat|json|ya?ml))
    """
)
_D3_INLINE = re.compile(r"(?i)(?:\s-c\s|\s--command\b|\s-command\b|\s-e\s|\s--eval\b)")

# D4 - a deliverable concat or a/v mux done by hand.
_D4_FFMPEG = re.compile(r"(?i)\bffmpeg(?:\.exe)?\b")
_D4_CONCAT = re.compile(r"(?i)(?:\s-f\s+concat\b|filter_complex[^\n]*\bconcat\b|\bconcat\s*=)")
_D4_STREAMCOPY = re.compile(r"(?i)\s-c(?::[av])?\s+copy\b")
_D4_INPUT = re.compile(r"(?i)(?:^|\s)-i\s+\S+")
_D4_OUTPUT = re.compile(r"(?i)\.(?:mp4|mov|mkv|m4v|avi|webm|mxf)\b")
_D4_NULL = re.compile(r"(?i)\s-f\s+null\b")
_SOX_EXT = r"(?:wav|flac|aiff|au)"
_D4_SOX = re.compile(
    rf"""(?i)^\s*sox\b.*?\.{_SOX_EXT}\s+.*?\.{_SOX_EXT}\s+
    \S+\.(?:wav|flac|mp3|ogg|aiff)\s*$""",
    re.X,
)

# D5 - a raw publish where the repo declares no release lane.
_D5 = re.compile(
    r"""(?xi)(?:^|[;&|(]\s*)
    (?: gh\s+release\s+(?:create|upload|edit)
      | npm\s+publish | yarn\s+publish | pnpm\s+publish
      | twine\s+upload | docker\s+push | podman\s+push
      | cargo\s+publish | gem\s+push )
    \b"""
)

# D6 - hand-rolled orchestration.
_D6_LOOP = re.compile(
    r"(?is)(?:^|[;&|(]\s*)(?:until|while)\b[\s\S]{0,2000}?\bdo\b"
    r"[\s\S]{0,2000}?\b(?:sleep|start-sleep|wait)\b[\s\S]{0,2000}?\bdone\b"
)
_D6_DETACH = re.compile(r"(?i)\b(?:nohup|disown|setsid)\b")
_D6_AMP = re.compile(r"(?<![&>])&(?=\s*(?:$|[\n;)]))")

# D7 - killing a lock/lease or a platform daemon by hand.
_D7_RM = re.compile(r"(?i)(?:^|[;&|(]\s*)(?:rm|rmdir|Remove-Item)\b(?=[^\n]*\s-{1,2}[a-z]*[rf])")
_D7_LOCK = re.compile(r"(?i)(?:^|[/\\])lock(?:dir|s)?(?:[/\\]|$)|\.lock\b|\.lease\b|\blockfile\b")
_D7_TASKKILL = re.compile(r"(?i)\btaskkill\b")
_D7_STOPP = re.compile(r"(?i)\bStop-Process\b")
_PLATFORM_DAEMONS = re.compile(
    r"(?i)\b(?:genesis|awsh|awdk|awrelay|awm|hookd|spine|fleet|awsettings|guardiand|awsupervise)\b"
)

_STEER = {
    "D1": (
        "awrun (queue it: mcp__aitheros__awsh_awrun_queue) for a job that must run detached; "
        "mediaforge_run_op op=film_render for a render; mcp__aitheros__desktop_open / awdesk_run "
        "to launch a desktop app (wslg included)"
    ),
    "D2": (
        "mcp__aitheros__fleet_control (or mcp__aitheros__awsh_*) and the documented fleet-deploy "
        "op; never edit live systemd units or run a host temp script through nsenter"
    ),
    "D3": (
        "awgit wt new <name> and write the file in that worktree, then run the owning lane - "
        "awrun, awsh_awrun_queue, mediaforge_run_op, tasks_job_schedule"
    ),
    "D4": (
        "mediaforge_run_op op=film_assemble (concat / EDL), op=mux_audio (picture + audio), "
        "or op=film_render - these already exist in media-forge and are the delivery path"
    ),
    "D5": (
        "the repo's declared release workflow (gh workflow run <release>.yml) or awrel; a client "
        "delivery belongs in a delivery lane, not in hand-written release notes"
    ),
    "D6": (
        "mcp__aitheros__awsh_awrun_queue, mcp__aitheros__tasks_job_schedule, or a "
        "routine declared to the scheduler (a routine file, not a loop in a shell)"
    ),
    "D7": (
        "awgit lease release <path> for a lock or lease; the owning platform CLI (awsettings, "
        "awrun, awsh) or the aw_ops.py platform tool for a process"
    ),
}

_TITLE = {
    "D1": "a detached launcher started by hand",
    "D2": "a raw fleet shell",
    "D3": "generated code writing outside any work tree",
    "D4": "a hand-built media concat or mux",
    "D5": "a raw publish with no declared release lane",
    "D6": "hand-rolled orchestration",
    "D7": "a hand-killed lock or daemon",
}


def _d1(cmd: str, cwd: Optional[str], env: Dict[str, str]) -> bool:
    return bool(_D1_LAUNCH.search(cmd)) and bool(_D1_TARGET.search(cmd))


def _d2(cmd: str, cwd: Optional[str], env: Dict[str, str]) -> bool:
    return bool(_D2.search(cmd))


def _d3(cmd: str, cwd: Optional[str], env: Dict[str, str]) -> bool:
    bodies: List[str] = []
    for head, body in heredoc_blocks(cmd):
        if _INTERP.search(head):
            bodies.append(head + "\n" + body)
    for step in split_steps(cmd):
        s = step.strip()
        if _INTERP_POS.match(s) and _D3_INLINE.search(s):
            bodies.append(s)
    for text in bodies:
        if not _D3_WRITE.search(text):
            continue
        for m in _D3_TARGETS_RE.finditer(text):
            path = m.group(1) or m.group(2)
            if path and not _in_git_worktree(path, cwd):
                return True
    return False


def _d4(step: str, cwd: Optional[str], env: Dict[str, str]) -> bool:
    if _D4_SOX.search(step):
        return True
    if not _D4_FFMPEG.search(step):
        return False
    if _D4_CONCAT.search(step):
        return True
    if _D4_NULL.search(step):
        return False
    if _D4_STREAMCOPY.search(step) and _D4_OUTPUT.search(step):
        return True
    inputs = len(_D4_INPUT.findall(step))
    return inputs >= 2 and bool(_D4_OUTPUT.search(step))


def _d5(step: str, cwd: Optional[str], env: Dict[str, str]) -> bool:
    if not _D5.search(step):
        return False
    return not _release_lane(cwd, env)


def _d6(cmd: str, cwd: Optional[str], env: Dict[str, str]) -> bool:
    return bool(_D6_LOOP.search(cmd) or _D6_DETACH.search(cmd) or _D6_AMP.search(cmd))


def _d7(step: str, cwd: Optional[str], env: Dict[str, str]) -> bool:
    if _D7_TASKKILL.search(step):
        return True
    if _D7_RM.search(step) and _D7_LOCK.search(step):
        return True
    return bool(_D7_STOPP.search(step) and _PLATFORM_DAEMONS.search(step))


#: The rule table. ONE list, evaluated in order. ``scope`` says what string the
#: test receives: the RAW command (needs what quotes hold), the MASKED command
#: (structure over the whole line) or each STEP (a single command).
RULES: List[Dict[str, Any]] = [
    {
        "id": "D1", "scope": "raw", "test": _d1,
        "sample": 'Start-Process -FilePath "C:\\Program Files\\Git\\bin\\bash.exe" '
                  "-ArgumentList 'E:/Aither-Media/x/shoot/v10.1/render.sh' -WindowStyle Hidden",
        "expect": "deny",
    },
    {
        "id": "D2", "scope": "raw", "test": _d2,
        "sample": "wsl -d awnix -u root -- nsenter -t 1 -m -- sh "
                  "/mnt/c/Users/wzns/AppData/Local/Temp/kokoro-unit-fix.sh --apply",
        "expect": "deny",
    },
    {
        "id": "D3", "scope": "raw", "test": _d3,
        "sample": "python - <<'PY'\nopen('place_stall_cars_v3c.json','w').write('[]')\nPY",
        "expect": "deny",
    },
    {
        "id": "D4", "scope": "step", "test": _d4,
        "sample": "ffmpeg -f concat -safe 0 -i list.txt -c copy out.mp4",
        "expect": "deny",
    },
    {
        "id": "D5", "scope": "step", "test": _d5,
        "sample": "gh release create v1.2.0 --repo customer/repo -n 'notes'",
        "expect": "deny",
    },
    {
        "id": "D6", "scope": "masked", "test": _d6,
        "sample": "until grep -q DONE log; do sleep 60; done; bash assemble.sh",
        "expect": "deny",
    },
    {
        "id": "D7", "scope": "step", "test": _d7,
        "sample": "rm -rf /c/Users/wzns/.aither/lock",
        "expect": "deny",
    },
]


def reason_for(rule: Dict[str, Any]) -> str:
    """The refusal text. Never contains the command: it may carry a secret."""
    return (
        f"{RULE_PREFIX} (rule {rule['id']}: {_TITLE.get(rule['id'], rule['id'])}) - this does the "
        "job by hand and bypasses the lane that owns it.\n"
        f"Use instead: {_STEER.get(rule['id'], 'the platform lane for this job')}\n"
        "The owner's standing rule (2026-11-18, fifth time): never hand-roll a script, never start "
        f"a bare process, find-and-extend before building - {PRIORITY_SENTENCE}\n"
        f"One deliberate exception: prefix the command with {BYPASS_ENV}=1 (allowed, and one "
        "redacted row is appended under ~/.aither/platform_first/). "
        f"Disable the guard entirely with {OFF_ENV}=1."
    )


# ---------------------------------------------------------------------------
# THE DECISION
# ---------------------------------------------------------------------------

def _verdict(command: str, cwd: Optional[str], env: Dict[str, str]) -> Optional[Dict[str, Any]]:
    masked = _mask(command)
    steps = [s for s in split_steps(masked) if s.strip()]
    if not steps:
        return None
    # Every step legitimate -> no rule has anything to act on. This is the
    # zero-cost path for `ls`, `git status`, `grep -rn "Start-Process" .`.
    if all(is_allowed(s) for s in steps):
        return None
    for rule in RULES:
        scope = rule["scope"]
        try:
            if scope == "raw":
                hit = rule["test"](command, cwd, env)
            elif scope == "masked":
                hit = rule["test"](masked, cwd, env)
            else:
                hit = any(rule["test"](s, cwd, env) for s in steps if not is_allowed(s))
        except Exception:  # noqa: BLE001 - a rule that crashes must not deny
            hit = False
        if hit:
            return rule
    return None


def _log_bypass(rule_id: Optional[str], command: str, payload: Dict[str, Any],
                env: Dict[str, str]) -> None:
    """One redacted row per deliberate bypass. Never the command itself."""
    try:
        base = Path(env.get(LOG_DIR_ENV) or (Path.home() / ".aither" / "platform_first"))
        base.mkdir(parents=True, exist_ok=True)
        day = datetime.date.today().isoformat()
        row = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "session_id": payload.get("session_id"),
            "rule": rule_id,
            "sha256": hashlib.sha256(command.encode("utf-8", "replace")).hexdigest(),
            # The program and its first argument only, capped at 80 chars: a short
            # command logged as a prefix would be the WHOLE command, secret included.
            "head": " ".join(command.split()[:2])[:80],
        }
        with (base / f"bypass-{day}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception as exc:  # noqa: BLE001 - a log that cannot write must not block the call
        _warn_once("bypass-log", f"could not append the bypass row ({exc})")


def decide(payload: Any, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Judge a PreToolUse payload.

    Returns ``{"action": "allow"|"deny", "rule": id|None, "reason": str|None,
    "note": str|None}``. An unknown shape, an unguarded tool or any exception is
    an ALLOW - the guard is advice with teeth, not a crash.
    """
    env = dict(os.environ if env is None else env)
    try:
        if not isinstance(payload, dict):
            return {"action": "allow", "rule": None, "reason": None, "note": None}
        if payload.get("tool_name") not in GUARDED_TOOLS:
            return {"action": "allow", "rule": None, "reason": None, "note": None}
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return {"action": "allow", "rule": None, "reason": None, "note": None}
        command = tool_input.get("command")
        if not isinstance(command, str) or not command.strip():
            return {"action": "allow", "rule": None, "reason": None, "note": None}

        if env.get(OFF_ENV, "").strip().lower() in ("1", "true", "yes"):
            return {
                "action": "allow", "rule": None, "reason": None,
                "note": (f"{RULE_PREFIX}: guard DISABLED by {OFF_ENV} - hand-rolled commands in "
                         "this session will not be refused"),
            }

        cwd = payload.get("cwd") or env.get("CLAUDE_PROJECT_DIR") or None
        rule = _verdict(command, cwd, env)
        if rule is None:
            return {"action": "allow", "rule": None, "reason": None, "note": None}

        bypass = env.get(BYPASS_ENV, "").strip().lower() in ("1", "true", "yes")
        if not bypass:
            stripped = command.lstrip()
            bypass = re.match(rf"(?i)^{BYPASS_ENV}=1\s+", stripped) is not None
            if bypass:
                command = re.sub(rf"(?i)^{BYPASS_ENV}=1\s+", "", stripped, count=1)
        if bypass:
            _log_bypass(rule["id"], command, payload, env)
            return {"action": "allow", "rule": rule["id"], "reason": None,
                    "note": f"{RULE_PREFIX}: {rule['id']} bypassed once via {BYPASS_ENV} (logged)"}
        return {"action": "deny", "rule": rule["id"], "reason": reason_for(rule), "note": None}
    except Exception:  # noqa: BLE001 - fail open, documented at module top
        return {"action": "allow", "rule": None, "reason": None, "note": None}


def guard_main(stdin: Any = None, stdout: Any = None, stderr: Any = None,
               mode: str = "") -> int:
    """PreToolUse entry point. JSON deny contract by default, exit-2 on request."""
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    mode = (mode or os.environ.get(MODE_ENV, "") or "json").strip().lower()
    try:
        payload = json.load(stdin)
    except Exception:  # noqa: BLE001 - a malformed payload is not a refusal
        return 0
    verdict = decide(payload)
    if verdict.get("note"):
        _emit(stderr, verdict["note"])
    if verdict["action"] != "deny":
        return 0
    if mode in ("exit2", "stderr"):
        _emit(stderr, verdict["reason"])
        return 2
    try:
        json.dump({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": verdict["reason"],
        }}, stdout)
    except Exception:  # noqa: BLE001
        return 0
    return 0


# ---------------------------------------------------------------------------
# FIXTURES - one per case the owner actually hit, plus the legit list.
# ---------------------------------------------------------------------------

def _payload(command: str, cwd: Optional[str] = None, tool: str = "Bash") -> Dict[str, Any]:
    out: Dict[str, Any] = {"tool_name": tool, "tool_input": {"command": command},
                           "session_id": "self-test"}
    if cwd:
        out["cwd"] = cwd
    return out


class _StringIO:
    """A tiny in-memory text stream, standing in for stdin/stdout in self_test."""

    def __init__(self, initial: str = "") -> None:
        import io
        self._buf = io.StringIO(initial)

    def read(self) -> str:
        return self._buf.read()

    def write(self, s: str) -> int:
        return self._buf.write(s)

    def getvalue(self) -> str:
        return self._buf.getvalue()


def _mk_loose() -> str:
    import tempfile
    return tempfile.mkdtemp(prefix="pf-loose-")


def _mk_repo() -> str:
    import tempfile
    d = tempfile.mkdtemp(prefix="pf-repo-")
    os.makedirs(os.path.join(d, ".git"), exist_ok=True)
    return d


def cases() -> List[Dict[str, Any]]:
    """Every assertion --self-test makes. ``want`` is the action; ``rule`` pins the id."""
    loose = _mk_loose()
    repo = _mk_repo()
    return [
        # ---- DENY: today's seven violations -------------------------------
        {"name": "D1 Start-Process runs render.sh detached", "want": "deny", "rule": "D1",
         "payload": _payload('Start-Process -FilePath "C:\\Program Files\\Git\\bin\\bash.exe" '
                             "-ArgumentList 'E:/Aither-Media/x/shoot/v10.1/render.sh' "
                             "-WindowStyle Hidden", loose, "PowerShell")},
        {"name": "D1 Start-Process wslg.exe", "want": "deny", "rule": "D1",
         "payload": _payload("Start-Process wslg.exe", loose, "PowerShell")},
        {"name": "D2 nsenter runs a host temp script against the fleet", "want": "deny",
         "rule": "D2", "payload": _payload(
             "wsl -d awnix -u root -- nsenter -t 1 -m -- sh "
             "/mnt/c/Users/wzns/AppData/Local/Temp/kokoro-unit-fix.sh --apply")},
        {"name": "D2 podman exec of a host script", "want": "deny", "rule": "D2",
         "payload": _payload("wsl -d awnix -u root -- sh /mnt/c/tmp/x.sh")},
        {"name": "D3 heredoc writes a pack data file in a media dir", "want": "deny",
         "rule": "D3", "payload": _payload(
             "python - <<'PY'\nimport json\n"
             "open('place_stall_cars_v3c.json','w').write('[]')\nPY", loose)},
        {"name": "D3 python -c writes a loose script", "want": "deny", "rule": "D3",
         "payload": _payload("python -c \"open('/tmp/kokoro-check.sh','w').write('x')\"", loose)},
        {"name": "D4 ffmpeg concat to a deliverable", "want": "deny", "rule": "D4",
         "payload": _payload("ffmpeg -f concat -safe 0 -i list.txt -c copy out.mp4", loose)},
        {"name": "D4 ffmpeg two-input a/v mux", "want": "deny", "rule": "D4",
         "payload": _payload(
             "ffmpeg -i v.mp4 -i vo.wav -c:v copy -c:a aac final.mp4", loose)},
        {"name": "D5 gh release create with no declared lane", "want": "deny", "rule": "D5",
         "payload": _payload("gh release create v1.2.0 --repo customer/repo -n 'notes'", loose)},
        {"name": "D6 until/sleep loop then a build", "want": "deny", "rule": "D6",
         "payload": _payload(
             "until grep -q DONE log; do sleep 60; done; bash assemble.sh", loose)},
        {"name": "D6 nohup detached build", "want": "deny", "rule": "D6",
         "payload": _payload("nohup python build.py > log 2>&1 &", loose)},
        {"name": "D7 rm -rf of a lock directory", "want": "deny", "rule": "D7",
         "payload": _payload("rm -rf /c/Users/wzns/.aither/lock")},
        {"name": "D7 taskkill of a running job", "want": "deny", "rule": "D7",
         "payload": _payload("taskkill /F /PID 1234", loose, "PowerShell")},
        {"name": "D7 Stop-Process of a platform daemon", "want": "deny", "rule": "D7",
         # the container name is a PLACEHOLDER: the published copy of this module must
         # not carry an internal hostname (the package's own publish gate forbids it),
         # and the daemon match is on the role word, not the full name.
         "payload": _payload("Stop-Process -Name genesis-a", loose, "PowerShell")},

        # ---- ALLOW: the legit list ---------------------------------------
        {"name": "ALLOW ls -la", "want": "allow",
         "payload": _payload("ls -la", loose)},
        {"name": "ALLOW cat f", "want": "allow", "payload": _payload("cat f", loose)},
        {"name": "ALLOW grep -rn x .", "want": "allow",
         "payload": _payload("grep -rn x .", loose)},
        {"name": "ALLOW rg x", "want": "allow", "payload": _payload("rg x", loose)},
        {"name": "ALLOW a && chain of reads (not detached orchestration)", "want": "allow",
         "payload": _payload("git status --short && git log --oneline -3", loose)},
        {"name": "ALLOW a quoted ampersand", "want": "allow",
         "payload": _payload("grep -rn 'a & b' .", loose)},
        {"name": "ALLOW git status", "want": "allow",
         "payload": _payload("git status --short", loose)},
        {"name": "ALLOW git log --oneline -5", "want": "allow",
         "payload": _payload("git log --oneline -5", loose)},
        {"name": "ALLOW git diff", "want": "allow", "payload": _payload("git diff", loose)},
        {"name": "ALLOW gh pr view 123", "want": "allow",
         "payload": _payload("gh pr view 123", repo)},
        {"name": "ALLOW gh pr checks 123", "want": "allow",
         "payload": _payload("gh pr checks 123", repo)},
        {"name": "ALLOW the platform CLIs", "want": "allow",
         "payload": _payload("awgit status && awrun status && awkno -k render", repo)},
        {"name": "ALLOW awsettings --quiet pull", "want": "allow",
         "payload": _payload("awsettings --quiet --never-fail pull", repo)},
        {"name": "ALLOW awm recall", "want": "allow",
         "payload": _payload("awm recall --scope x --query y", repo)},
        {"name": "ALLOW adk chat atlas", "want": "allow",
         "payload": _payload("adk chat atlas", repo)},
        {"name": "ALLOW loopback health probe (media-forge ops)", "want": "allow",
         "payload": _payload("curl -s http://127.0.0.1:8200/ops", loose)},
        {"name": "ALLOW loopback TLS health probe", "want": "allow",
         "payload": _payload("curl -sk https://127.0.0.1:8150/health", loose)},
        {"name": "ALLOW dispatch Rung 2 fleet health", "want": "allow",
         # container name is a placeholder for the same reason as the D7 fixture
         "payload": _payload("wsl -d awnix -u root podman exec genesis-a "
                             "curl -sk https://localhost:8001/health", loose)},
        {"name": "ALLOW ffprobe", "want": "allow",
         "payload": _payload("ffprobe -v error -show_streams in.mp4", loose)},
        {"name": "ALLOW ffmpeg null-output probe", "want": "allow",
         "payload": _payload("ffmpeg -i in.mp4 -f null -", loose)},
        {"name": "ALLOW read-only inline analysis", "want": "allow",
         "payload": _payload("python - <<'PY'\n"
                             "print(sum(1 for l in open('x') if 'a' in l))\nPY", loose)},
        {"name": "ALLOW generated write INSIDE a worktree", "want": "allow",
         "payload": _payload("python - <<'PY'\nopen('data.json','w').write('{}')\nPY", repo)},
        {"name": "ALLOW a heredoc that merely documents the bypass", "want": "allow",
         "payload": _payload("cat <<'EOF'\nnever run ffmpeg -f concat -i l.txt -c copy o.mp4\n"
                             "EOF", loose)},
        {"name": "ALLOW grep for a refused shape", "want": "allow",
         "payload": _payload("grep -rn Start-Process .claude/hooks", loose)},
        {"name": "ALLOW the repo gates", "want": "allow",
         "payload": _payload("python tools/pr_local_verify.py 123 --post", repo)},
        {"name": "ALLOW pr_local_review", "want": "allow",
         "payload": _payload("python tools/pr_local_review.py 123 --comment", repo)},
        {"name": "ALLOW awgit pr merge", "want": "allow",
         "payload": _payload("awgit pr merge 123", repo)},
        {"name": "ALLOW the deploy-tree sync", "want": "allow",
         "payload": _payload("bash scripts/sync-deploy-tree.sh", repo)},
        {"name": "ALLOW git commit with a pathspec", "want": "allow",
         "payload": _payload("git commit -m x -- a.py", repo)},
        {"name": "ALLOW gh pr create inside a worktree", "want": "allow",
         "payload": _payload("gh pr create --fill", repo)},
        {"name": "ALLOW pytest", "want": "allow",
         "payload": _payload("python -m pytest -q", repo)},
    ]


def self_test() -> int:
    """Every fixture above, plus the escape hatches and the fail-open contract."""
    failures: List[str] = []
    n = 0
    for case in cases():
        n += 1
        got = decide(case["payload"], env={"PATH": ""})
        if got["action"] != case["want"]:
            failures.append(f"{case['name']}: want {case['want']}, got {got['action']} "
                            f"({got.get('rule')})")
        elif case.get("rule") and got.get("rule") != case["rule"]:
            failures.append(f"{case['name']}: want rule {case['rule']}, got {got.get('rule')}")
        if not failures or not failures[-1].startswith(case["name"]):
            print(f"ok: {case['name']}")

    # escape hatch: allowed, exactly one redacted row
    import tempfile
    logdir = tempfile.mkdtemp(prefix="pf-log-")
    env = {"PATH": "", BYPASS_ENV: "1", LOG_DIR_ENV: logdir}
    long_cmd = ("ffmpeg -f concat -safe 0 -i " + ", ".join(f"clips/take_{i:03d}.mov"
                                                           for i in range(12))
                + " -c copy out.mp4")
    got = decide(_payload(long_cmd, logdir), env=env)
    n += 1
    rows: List[str] = []
    for f in Path(logdir).glob("bypass-*.jsonl"):
        rows.extend(f.read_text(encoding="utf-8").splitlines())
    if got["action"] != "allow":
        failures.append("ESCAPE HATCH: AW_PLATFORM_FIRST_OK=1 did not allow")
    elif got["rule"] != "D4":
        failures.append(f"ESCAPE HATCH: logged rule {got['rule']}, want D4")
    elif len(rows) != 1:
        failures.append(f"ESCAPE HATCH: {len(rows)} bypass rows, want 1")
    else:
        row = json.loads(rows[0])
        if row.get("rule") != "D4" or len(row.get("head", "")) > 80 or "sha256" not in row:
            failures.append(f"ESCAPE HATCH: malformed row {row}")
        elif long_cmd in json.dumps(row) or row["head"] == long_cmd:
            failures.append("ESCAPE HATCH: row carries the whole command")
        else:
            print("ok: ESCAPE HATCH allows once and appends one redacted row")

    # the inline prefix form of the same hatch
    n += 1
    got = decide(_payload(f"{BYPASS_ENV}=1 ffmpeg -f concat -i l.txt -c copy out.mp4", logdir),
                 env={"PATH": "", LOG_DIR_ENV: logdir})
    if got["action"] == "allow":
        print("ok: ESCAPE HATCH as an inline command prefix")
    else:
        failures.append("ESCAPE HATCH: inline AW_PLATFORM_FIRST_OK=1 prefix did not allow")

    # OFF is loud and allows
    n += 1
    got = decide(_payload("ffmpeg -f concat -i l.txt -c copy out.mp4", logdir),
                 env={"PATH": "", OFF_ENV: "1"})
    if got["action"] == "allow" and got.get("note"):
        print("ok: AW_PLATFORM_FIRST_OFF=1 disables the guard and says so")
    else:
        failures.append("OFF: did not allow with a note")

    # fail-open
    for name, payload in (
        ("FAIL-OPEN: stdin is not json", None),
        ("FAIL-OPEN: an unguarded tool", {"tool_name": "Read", "tool_input": {"file_path": "x"}}),
        ("FAIL-OPEN: tool_input is a string", {"tool_name": "Bash", "tool_input": "ls"}),
        ("FAIL-OPEN: no command", {"tool_name": "Bash", "tool_input": {}}),
    ):
        n += 1
        if decide(payload, env={"PATH": ""})["action"] == "allow":
            print(f"ok: {name}")
        else:
            failures.append(f"{name}: denied")
    n += 1
    out, err = _StringIO(), _StringIO()
    code = guard_main(stdin=_StringIO("not json"), stdout=out, stderr=err)
    if code == 0 and out.getvalue() == "":
        print("ok: FAIL-OPEN: guard_main exits 0 silently on a malformed payload")
    else:
        failures.append(f"FAIL-OPEN: guard_main returned {code} / {out.getvalue()!r}")

    # the deny contract both ways
    payload = _payload("ffmpeg -f concat -i l.txt -c copy out.mp4")
    out = _StringIO()
    code = guard_main(stdin=_StringIO(json.dumps(payload)), stdout=out, stderr=_StringIO())
    n += 1
    try:
        body = json.loads(out.getvalue())
        ok_json = (code == 0
                   and body["hookSpecificOutput"]["permissionDecision"] == "deny"
                   and "D4" in body["hookSpecificOutput"]["permissionDecisionReason"]
                   and "film_assemble" in body["hookSpecificOutput"]["permissionDecisionReason"]
                   and PRIORITY_SENTENCE[:40] in
                   body["hookSpecificOutput"]["permissionDecisionReason"])
    except Exception:  # noqa: BLE001
        ok_json = False
    if ok_json:
        print("ok: JSON deny contract names the rule, the lane and the priority-1 sentence")
    else:
        failures.append("JSON deny contract: malformed or missing the lane/priority sentence")

    n += 1
    err = _StringIO()
    code = guard_main(stdin=_StringIO(json.dumps(payload)), stdout=_StringIO(),
                      stderr=err, mode="exit2")
    if code == 2 and "D4" in err.getvalue():
        print("ok: exit-2 deny contract for the repo hook and the awskills twin")
    else:
        failures.append(f"exit-2 contract: code {code}, stderr {err.getvalue()[:80]!r}")

    if failures:
        print("\n".join(f"FAIL: {f}" for f in failures))
        print(f"self-test: {len(failures)} of {n} assertions FAILED")
        return 1
    print(f"self-test: {n} assertions ok (D1..D7 deny, the legit list allows, both escape "
          "hatches and fail-open hold)")
    return 0


def list_rules() -> int:
    print(f"{RULE_PREFIX} v{VERSION} - {len(RULES)} deny rules, "
          f"{len(ALLOW_PREFIXES)} allow prefixes, {len(ALLOW_REGEX)} allow regexes")
    for rule in RULES:
        print(f"{rule['id']}  [{rule['scope']}]  {_TITLE.get(rule['id'], '')}")
        print(f"    proves it: {rule['sample']}")
        print(f"    instead:  {_STEER.get(rule['id'], '')}")
    return 0


def metrics(iterations: int = 1000) -> int:
    """Median/p95 decide() cost. The budget is 5 ms; a regression is a red gate."""
    import time
    payloads = [c["payload"] for c in cases()]
    env = {"PATH": ""}
    for p in payloads:  # warm the worktree cache
        decide(p, env=env)
    times: List[float] = []
    for i in range(iterations):
        t0 = time.perf_counter()
        decide(payloads[i % len(payloads)], env=env)
        times.append((time.perf_counter() - t0) * 1000.0)
    times.sort()
    median = times[len(times) // 2]
    p95 = times[int(len(times) * 0.95)]
    print(f"decide(): median {median:.3f} ms, p95 {p95:.3f} ms over {iterations} payloads "
          f"(budget 5 ms)")
    return 0 if median < 5.0 else 1


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in args:
        return self_test()
    if "--list-rules" in args:
        return list_rules()
    if "--metrics" in args:
        return metrics()
    return guard_main(mode="exit2" if "--exit2" in args else "")


if __name__ == "__main__":
    sys.exit(main())
