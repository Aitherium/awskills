#!/usr/bin/env python3
# Portable twin of the monorepo's pre-bash git guard, rendered by
# a render script from the monorepo (its PreToolUse git guard is the source) -- edit that hook, not this file.
# Worktree markers: GIT_GUARD_WORKTREE_MARKERS="name1,name2" (default: the current directory name).
"""PreToolUse (Bash) guard: refuse raw, worktree-wide git in this SHARED checkout.

    echo '{"tool_name":"Bash","tool_input":{"command":"git reset --hard"}}' | python <this>
      -> exit 2 + a stderr explanation
    python pre_bash_git_guard.py --self-test

Exit 2 = BLOCK (Claude Code feeds stderr back to the model). Exit 0 = allow.

WHY (2026-09-02): the concurrent-safe-git skill has mandated `awgit` for weeks.
At 10:31 a peer Claude session ran `git merge origin/develop` (ort + fast-forward)
plus a commit straight against <your repo> with no pathspec. Every STAGED
new file of another session vanished from disk (53 rule files, hooks, checkers) and
every modified tracked file reverted to HEAD; recovery took an hour of dangling-blob
forensics and transcript replay. The rule was documented, quoted, and ignored under
load. A rule nothing enforces is a suggestion; this hook is the enforcement.

WHAT IS BLOCKED (in this worktree only):
  git merge | rebase | pull | stash (push/apply/pop/drop/clear) | clean
  git reset            without a `--`/pathspec (i.e. anything that moves HEAD/index wholesale)
  git checkout/switch  to a ref without `--` pathspec (branch switch)
  git commit           without a pathspec or -o/--only (sweeps peers' staged work)
WHAT IS ALLOWED: every read (status/log/diff/show/ls-files/ls-tree/fsck/cat-file/
reflog/blame/branch listing/stash list|show), `git add`, `git restore`, pathspec'd
checkout/reset/commit, everything through `awgit`, and git run OUTSIDE this worktree
(a `cd` to another repo on the same line, or wsl/podman-hosted git).
Escape hatch: prefix the command with `GIT_GUARD_OK=1 ` - a visible, logged decision.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

WORKTREE_MARKERS = tuple(m for m in os.environ.get("GIT_GUARD_WORKTREE_MARKERS", "").split(",") if m) or (os.path.basename(os.getcwd()),)
BLOCK_ALWAYS = {"merge", "rebase", "pull", "clean"}
STASH_MUTATING = {"push", "save", "apply", "pop", "drop", "clear", "branch", ""}
_SPLIT = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")
#: A shell redirection token: `2>/dev/null`, `>out`, `2>&1`, `&>x`, `1>>log`.
#: These never reach git's argv, so they must never be read as a git subcommand.
_REDIR = re.compile(r"^(?:\d*|&)[<>]{1,2}")
_GIT = re.compile(r"(?:^|\s)git\s+(?:-C\s+\S+\s+|-c\s+\S+\s+|--no-pager\s+)*([a-z-]+)(.*)$")
# Quoted text is DATA, not a command. The first live block this guard ever made
# (2026-09-02) was its own author's `awgit blob-commit -m "... blocks raw git merge ..."`
# - the commit message named the thing being guarded. Blank every quoted span
# before looking for git verbs; a `--` pathspec marker is never inside quotes.
#: SINGLE quotes are inert: bash expands NOTHING inside them, and a backslash is
#: not an escape there either, so the span runs to the next quote. DOUBLE quotes
#: still expand `$(...)`, which is why the two are handled at different moments.
_SQUOTED = re.compile(r"'[^']*'", re.S)
_DQUOTED = re.compile(r'"(?:[^"\\]|\\.)*"', re.S)
_QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'', re.S)
#: `cmd <<EOF`, `<<-'EOF'`, `<<~"EOF"` - the body that follows is DATA.
_HEREDOC = re.compile(r"<<[-~]?\s*[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?")


#: `$(...)` and backticks. Their bodies EXECUTE - the opposite of quoted spans
#: and heredocs, which are data.
#: A BACKSLASH-escaped `\$(` or a backslash-escaped backtick is a literal, not an
#: expansion - bash does not run it. Without this lookbehind the guard refused its
#: own commit message documenting the bypass, which is the heredoc false positive
#: wearing a third face: describing a dangerous command must never read as issuing
#: one. The unescaped forms still execute and are still surfaced.
_SUBST = re.compile(r"(?<!\\)\$\(([^()]*)\)|(?<!\\)`([^`]*)`")


def _explode_substitutions(command: str) -> str:
    """Append every command-substitution body as its own segment.

    The mirror image of the data rules, and a REAL bypass found 2026-09-02 while
    checking a claim I had made to a peer: I said `$(...)` was "also data a guard
    could misread". It is not - it EXECUTES. Measured, before this fix:

        echo $(git merge origin/develop)   -> ALLOWED  (and it runs the merge)
        X=`git reset --hard`               -> ALLOWED

    because the verb is preceded by `(` or a backtick rather than whitespace, so
    the git matcher never saw it. Blanking these, as the note to the peer implied,
    would have cemented the hole instead of closing it.

    Runs BEFORE quoted spans are blanked, because bash expands `$(...)` inside
    double quotes too: `echo "$(git merge x)"` really does merge.
    """
    inner = [(m.group(1) or m.group(2) or "").strip() for m in _SUBST.finditer(command)]
    return command + "".join("; " + s for s in inner if s)


def _blank_heredocs(command: str) -> str:
    """Blank heredoc BODIES; keep the opening line and the terminator.

    Found 2026-09-02 by a peer, one layer under the quoted-span fix: quoted
    spans were blanked but a heredoc body was still judged as command text, so

        cat > notes.md <<MD
        | `cd .worktrees/x && git commit` | BLOCKED |
        MD

    was refused. That is not a rare shape - it refused the peer's `gh pr create
    --body` describing this very rule, and their commit message twice, because
    each DOCUMENTED the defect. Of everything a guard could refuse, refusing to
    write down what a dangerous command does is the worst: it teaches people to
    document less, and the workaround they find is sending less context rather
    than writing safer commands.
    """
    lines = command.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        out.append(lines[i])
        m = _HEREDOC.search(lines[i])
        if m:
            delim = m.group(1)
            i += 1
            while i < len(lines) and lines[i].strip() != delim:
                out.append("")
                i += 1
            if i < len(lines):
                out.append(lines[i])
        i += 1
    return "\n".join(out)


#: `cd <p>` or `git -C <p>` naming a path inside a .worktrees/ tree.
_WT_TARGET = re.compile(r"(?:^|\s)(?:cd|git\s+-C)\s+\"?([^\"\s]*[.]worktrees[/\\][^\"\s]+)")
#: Any git subcommand that WRITES. A zombie worktree makes these hit the main repo.
_GIT_WRITES = ("commit", "add", "rm", "mv", "restore", "apply", "am", "revert",
               "cherry-pick", "update-index", "write-tree", "commit-tree", "gc", "prune")


def _zombie_worktree(path: str) -> bool:
    """A .worktrees/<name> directory git no longer tracks.

    `awgit worktree rm` has twice left one behind (2026-09-02): unregistered with
    git, directory still on disk. Its own error text warns that a git command run
    inside it silently operates on <your repo> instead - confirmed live,
    `git -C .worktrees/<name> status` returned the MAIN repo's status. So a commit
    a session believes is isolated lands in the shared tree, which is this guard's
    whole subject. A real worktree always has a `.git` FILE pointing at its admin
    dir; a zombie has none.
    """
    try:
        p = Path(path)
        return p.is_dir() and not (p / ".git").exists()
    except OSError:
        return False


def verdict(command: str, cwd: str = "") -> str | None:
    """Return a block reason, or None to allow."""
    if os.environ.get("GIT_GUARD_OK") == "1" or command.lstrip().startswith("GIT_GUARD_OK=1"):
        return None
    # Order is load-bearing, and it is exactly the data/execution split:
    #   1. heredoc bodies      DATA      - blank
    #   2. single-quoted spans DATA      - blank (bash expands nothing inside them)
    #   3. $(...) / backticks  EXECUTION - surface as their own segments
    #   4. double-quoted spans mixed     - blank what is LEFT after step 3
    # Step 2 must precede step 3 or a substitution quoted for DISPLAY is surfaced
    # as a command (a peer hit exactly that: `probe 'echo $(git merge x)'` refused,
    # though bash would never run it). Step 3 must precede step 4 or the genuinely
    # executable `"$(git merge x)"` is lost with the quotes around it.
    command = _blank_heredocs(command)
    command = _SQUOTED.sub("''", command)
    command = _DQUOTED.sub('""', _explode_substitutions(command))
    wt = _WT_TARGET.search(command)
    _write_re = (r"(?:^|\s)git\s+(?:-C\s+\S+\s+|-c\s+\S+\s+|--no-pager\s+)*("
                 + "|".join(_GIT_WRITES) + r")\b")
    if wt and _zombie_worktree(wt.group(1)) and re.search(_write_re, command):
        return (f"`{wt.group(1)}` is a ZOMBIE worktree (no .git pointer): git inside it "
                "silently operates on the MAIN shared repo, so an 'isolated' commit lands "
                "in everyone's tree. Recreate it with `awgit worktree new`, or work in the "
                "main tree deliberately")
    if "wsl " in command or "podman " in command:
        return None  # git inside the distro / a container is not this worktree
    for seg in _SPLIT.split(command):
        if re.search(r"(?:^|\s)cd\s+", seg) and not any(m in seg for m in WORKTREE_MARKERS):
            return None  # the line moves to another repo first
        m = _GIT.search(seg)
        if not m or seg.lstrip().startswith("awgit"):
            continue
        sub, rest = m.group(1), m.group(2)
        # STRIP REDIRECTIONS BEFORE ANY RULE READS args[0].
        #
        # Measured 2026-09-10, and it cost a real incident: `git stash
        # 2>/dev/null >/dev/null` was ALLOWED. The shell gives those tokens to
        # the kernel, never to git, but `rest.split()` handed them over as
        # positional arguments -- so `args[0]` was "2>/dev/null", which is not in
        # STASH_MUTATING, and the repo-global stash read as a harmless read-only
        # subcommand like `stash list`. A whole shared worktree was swept (every
        # peer's tracked modifications; untracked survived -- the an earlier ledgered incident damage
        # signature) while this guard, installed to prevent exactly that,
        # returned None. It then correctly blocked the `git stash pop` that
        # restored it, which is the tell: the guard was live the whole time.
        #
        # The hole is not stash-specific -- every rule below that inspects
        # args[0] (branch, checkout, switch) can be defeated by a leading
        # redirection -- so it is fixed here, once, at the tokenizer.
        args = [a for a in rest.split()
                if not _REDIR.match(a) and not a.startswith(("<", ">"))]
        has_pathspec = "--" in args
        if sub in BLOCK_ALWAYS:
            return f"`git {sub}` rewrites the shared worktree/HEAD for every session"
        # Ref-moving plumbing. Found 2026-09-02 by a peer probing this guard: it
        # blocked `reset --hard` while ALLOWING three commands with the same or a
        # LARGER blast radius. `update-ref` and `branch -f` move a shared branch
        # wholesale exactly as a reset does; `push --force` is worse, destroying
        # work on the REMOTE for everyone rather than just on this box. A guard
        # that stops the loud form and passes the quiet one is the shape it exists
        # to prevent. (awgit's own internal update-ref is unaffected - this reads
        # the Bash command line, and awgit is a single argv token.)
        if sub == "update-ref":
            return ("`git update-ref` moves a shared branch ref wholesale, exactly like the "
                    "reset this guard blocks; use `awgit blob-commit --advance`")
        if sub == "branch" and any(a in ("-f", "--force", "-D", "-M") for a in args):
            return (f"`git branch {args[0]}` force-moves or deletes a shared branch ref; "
                    "use `awgit blob-commit --advance`")
        if sub == "push" and any(
                a in ("-f", "--force") or a.startswith("--force-with-lease") for a in args):
            return ("`git push --force` destroys work on the REMOTE for every clone, not just "
                    "this box - the largest blast radius of anything this guard sees")
        if sub == "push" and any(a.startswith(":") for a in args):
            return ("a `:ref` push DELETES that remote branch (an empty SHA once deleted a "
                    "branch here); name the source ref explicitly")
        if sub == "stash" and (not args or args[0] in STASH_MUTATING):
            return "`git stash` is repo-global here: it removes OTHER sessions' work from disk"
        if sub == "reset" and not has_pathspec:
            return ("`git reset` without `-- <path>` moves index/HEAD for every session "
                    "(a peer did this on 2026-09-02 and deleted staged files)")
        if (sub in ("checkout", "switch") and not has_pathspec and args
                and not args[0].startswith("-b")):
            return f"`git {sub} <ref>` switches the shared checkout under every other session"
        if sub == "commit" and not has_pathspec and not any(a in ("-o", "--only") for a in args):
            return ("`git commit` without a pathspec sweeps peers' staged work; "
                    "use `awgit blob-commit ... <paths>`")
    return None


def self_test() -> int:
    n = 0

    def ck(name: str, ok: bool) -> None:
        nonlocal n
        n += 1
        if not ok:
            print("SELF-TEST FAIL: " + name)
            raise SystemExit(1)

    ck("merge blocked", verdict("git merge origin/develop") is not None)
    ck("pull blocked", verdict("cd /work/" + WORKTREE_MARKERS[0] + " && git pull") is not None)
    ck("reset --hard blocked", verdict("git reset --hard HEAD~1") is not None)
    ck("stash blocked", verdict("git stash") is not None)
    ck("stash push blocked", verdict("git stash push -u") is not None)
    ck("checkout branch blocked", verdict("git checkout develop") is not None)
    ck("bare commit blocked", verdict('git commit -m "x"') is not None)
    ck("compound: read then merge still blocked",
       verdict("git status && git merge x") is not None)
    ck("status allowed", verdict("git status --porcelain") is None)
    ck("log/diff/show allowed",
       verdict("git log -3; git diff HEAD -- a.py; git show HEAD:a.py") is None)
    ck("stash list allowed", verdict("git stash list") is None)
    # A REDIRECTION IS NOT A SUBCOMMAND. This guard ALLOWED
    # `git stash 2>/dev/null` until 2026-09-10: rest.split() handed the
    # redirection over as argv, args[0] was "2>/dev/null", it was not in
    # STASH_MUTATING, and a repo-global stash read as `stash list`. A shared
    # worktree was swept that day with this guard installed and live -- it then
    # blocked the `stash pop` that put it back, which is how the hole surfaced.
    ck("stash behind a redirection blocked",
       verdict("git stash 2>/dev/null >/dev/null") is not None)
    ck("compound: read-stash then silenced stash still blocked",
       verdict("git stash list >/dev/null; git stash 2>/dev/null") is not None)
    # The hole was never stash-specific: every rule reading args[0] was defeatable.
    ck("branch -f behind a redirection blocked",
       verdict("git branch 2>/dev/null -f develop abc") is not None)
    ck("checkout behind a redirection blocked",
       verdict("git checkout 2>/dev/null develop") is not None)
    ck("redirection on a read-only command still allowed",
       verdict("git log --oneline -1 2>/dev/null") is None)
    ck("add allowed", verdict("git add -- a.py b.py") is None)
    ck("pathspec reset allowed", verdict("git reset -- a.py") is None)
    ck("pathspec checkout allowed", verdict("git checkout stash@{0} -- docs/x.md") is None)
    ck("restore --staged allowed", verdict("git restore --staged -- a.py") is None)
    ck("pathspec commit allowed", verdict('git commit -m "x" -- a.py') is None)
    ck("awgit allowed", verdict("awgit blob-commit --base HEAD -m x a.py") is None)
    ck("other repo allowed", verdict("cd /d/persona && git pull") is None)
    ck("wsl-hosted git allowed", verdict("wsl -d Debian -u root git -C /opt/x pull") is None)
    ck("escape hatch honoured", verdict("GIT_GUARD_OK=1 git merge x") is None)
    # The 2026-09-02 peer probe: these three were ALLOWED while reset was blocked.
    ck("update-ref blocked", verdict("git update-ref refs/heads/develop HEAD~5") is not None)
    ck("branch -f blocked", verdict("git branch -f develop origin/main") is not None)
    ck("branch -D blocked", verdict("git branch -D feature/x") is not None)
    ck("push --force blocked", verdict("git push --force origin develop") is not None)
    ck("push --force-with-lease blocked",
       verdict("git push --force-with-lease origin develop") is not None)
    ck("ref-delete push blocked", verdict("git push origin :refs/heads/x") is not None)
    ck("plain push allowed", verdict("git push origin HEAD:refs/heads/backup/x") is None)
    ck("branch create allowed", verdict("git branch feature/new HEAD") is None)
    ck("branch listing allowed", verdict("git branch -a") is None)
    ck("fetch allowed", verdict("git fetch origin feat/x") is None)
    # Zombie worktree (reported live 2026-09-02 by a peer: `awgit worktree rm` left
    # one twice, and git inside it returned the MAIN repo's status).
    import tempfile as _tf
    with _tf.TemporaryDirectory() as _td:
        zombie = Path(_td) / ".worktrees" / "dead"
        zombie.mkdir(parents=True)
        live = Path(_td) / ".worktrees" / "alive"
        live.mkdir(parents=True)
        (live / ".git").write_text("gitdir: ../../.git/worktrees/alive\n", encoding="utf-8")
        z, a = zombie.as_posix(), live.as_posix()
        ck("write in a zombie worktree blocked",
           verdict(f'git -C {z} commit -m "x" -- a.py') is not None)
        ck("cd into a zombie then write blocked",
           verdict(f'cd {z} && git add -- a.py') is not None)
        ck("READ in a zombie is allowed (no write verb)",
           verdict(f"git -C {z} status --porcelain") is None)
        ck("write in a REAL worktree allowed",
           verdict(f'git -C {a} commit -m "x" -- a.py') is None)
        ck("nonexistent worktree path does not block (not a dir)",
           verdict(f'git -C {_td}/.worktrees/never commit -m "x" -- a.py') is None)
    ck("git verbs inside a quoted commit message are data, not commands",
       verdict('awgit blob-commit -m "blocks raw git merge; git reset too\nline 2" a.py') is None)
    ck("quoted text does not hide a real verb after it",
       verdict('echo "git status" && git merge x') is not None)
    # Heredoc bodies are DATA (peer-isolated 2026-09-02): documenting a dangerous
    # command must never read as issuing one, or people document less.
    ck("heredoc body documenting a dangerous command is allowed",
       verdict("cat > b.md <<MD\n| `cd .worktrees/x && git commit` | BLOCKED |\nMD\n") is None)
    ck("heredoc documenting merge/reset is allowed",
       verdict("cat <<'EOF' > doc.md\nnever run git merge or git reset --hard here\nEOF\n")
       is None)
    ck("a REAL command after a heredoc is still blocked",
       verdict("cat <<EOF > f.txt\nharmless text\nEOF\ngit merge origin/develop") is not None)
    ck("a real command BEFORE a heredoc is still blocked",
       verdict("git reset --hard && cat <<EOF > f.txt\ntext\nEOF") is not None)
    ck("indented <<- terminator still closes the body",
       verdict("cat <<-EOF > f.txt\n\tgit push --force origin develop\n\tEOF\n") is None)
    # Command substitution EXECUTES - the mirror of the data rules. These were a
    # live BYPASS until 2026-09-02: the verb sits after `(` or a backtick, so the
    # matcher never saw it. Do NOT "fix" a future false positive by blanking them.
    ck("$( ) substitution running a merge is blocked",
       verdict("echo $(git merge origin/develop)") is not None)
    ck("backtick substitution running a reset is blocked",
       verdict("X=`git reset --hard`") is not None)
    ck("substitution inside DOUBLE quotes is still blocked",
       verdict('echo "$(git merge origin/develop)"') is not None)
    ck("a read inside a substitution stays allowed",
       verdict("files=$(git ls-files | head)") is None)
    ck("a substitution with no git verb stays allowed",
       verdict("d=$(date +%s) && echo $d") is None)
    ck("a BACKSLASH-ESCAPED substitution is a literal, not an expansion",
       verdict(r'awgit blob-commit -m "before the fix: echo \$(git merge x) ran it" a.py')
       is None)
    ck("escaped backtick is a literal too",
       verdict(r'awgit blob-commit -m "and X=\`git reset --hard\` too" a.py') is None)
    # SINGLE-quoted is inert data (peer-pinned 2026-09-02): bash expands nothing
    # inside it, so quoting a substitution for DISPLAY must not read as running it.
    ck("single-quoted substitution is data, not execution",
       verdict("probe 'echo $(git merge origin/develop)'") is None)
    ck("single-quoted dangerous verb is data",
       verdict("echo 'git reset --hard is what broke it'") is None)
    ck("DOUBLE-quoted substitution still executes and is blocked",
       verdict('echo "$(git merge origin/develop)"') is not None)
    ck("blanking single quotes does not hide a real verb outside them",
       verdict("echo 'harmless' && git merge x") is not None)
    ck("a pathspec commit with a single-quoted message stays allowed",
       verdict("git commit -m 'fix the thing' -- a.py") is None)
    ck("pathspec commit with a scary message allowed",
       verdict('git commit -m "revert the git stash incident" -- a.py') is None)
    print(f"self-test: guard blocks the 2026-09-02 class and allows every read ({n} assertions)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return self_test()
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # never block on our own parse failure
    if payload.get("tool_name") != "Bash":
        return 0
    command = str((payload.get("tool_input") or {}).get("command", ""))
    reason = verdict(command, str(payload.get("cwd", "")))
    if reason is None:
        return 0
    sys.stderr.write(
        "GIT GUARD (concurrent-safe-git): BLOCKED - " + reason + ".\n"
        "This checkout is shared by several live sessions and a CD loop. Use `awgit` "
        "(`awgit blob-commit --base HEAD --advance -m msg <paths>`, `awgit fresh`, `awgit read`), "
        "or a pathspec form. To override deliberately, prefix: GIT_GUARD_OK=1 <command>\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
