#!/usr/bin/env bash
# agent-worktree-reaper.sh — find and safely reclaim git worktrees your AI agents
# created and never cleaned up.
#
# THE PROBLEM
# -----------
# Agent harnesses create a throwaway git worktree per isolated task (Claude Code's
# `isolation: "worktree"`, swarm/forge loops, parallel review fan-outs). The task
# ends, the worktree stays. Nothing reaps them.
#
# Measured on a real box (2026-07-26): `.claude/worktrees` held **295 GB across 32
# worktrees**, inside a checkout that had grown to **1.15 TB** — of which the actual
# `.git` was **4.7 GB**. Measured again 2026-10-04: 55 worktrees at ~1.8 GB each took
# the system drive to **10 MB free**; reaping 51 of them freed 80 GB.
#
# THE SAFETY GATE (get this wrong and you delete somebody's work)
# --------------------------------------------------------------
# A worktree is SAFE to delete only when it has:
#   1. no uncommitted changes            -> git status --porcelain (untracked counted,
#                                           build/cache dirs ignored)
#   2. no commits missing from a remote  -> git log HEAD --not --remotes
#   3. no activity for --min-idle-hours  -> newest of: git stamps AND the changed files
#
# 🪤 TRAP 1: `git log --branches --not --remotes` looks right and is WRONG. Worktrees
# share one object store, so `--branches` returns the SAME repo-wide count for every
# worktree. Anchor on `HEAD`.
#
# 🪤 TRAP 2: untracked files ARE work. An agent's new test file is untracked until it
# commits. `git diff HEAD` (the obvious archive) does not contain it, so an
# archive-then-delete built on it destroys exactly the newest work. (This script did
# that until 2026-10-04.) A DIRTY worktree is reaped only after a SNAPSHOT: tracked and
# untracked changes are committed into `refs/heads/reclaim/<name>` through a throwaway
# index, and every changed path is verified in that snapshot before anything is removed.
#
# 🪤 TRAP 3: git activity is not activity. A session editing files without staging
# touches no git stamp for hours. Idle time is therefore the newest of the HEAD reflog,
# the index, AND the mtimes of the changed files themselves.
#
# Usage:
#   agent-worktree-reaper.sh                        # audit only (default, read-only)
#   agent-worktree-reaper.sh --reap                 # remove the SAFE ones
#   agent-worktree-reaper.sh --reap --all           # also DIRTY ones, each snapshotted first
#   agent-worktree-reaper.sh --archive DIR ...      # also write a patch per dirty tree to DIR
#   agent-worktree-reaper.sh --min-idle-hours 6     # idle floor (default 2)
#   agent-worktree-reaper.sh --self-test            # prove the gate on a scratch repo
#   AGENT_WT_KEEP="a b" agent-worktree-reaper.sh --reap   # never touch these
#
# Restore a snapshotted worktree:  git worktree add <dir> reclaim/<name>
#
# Env:
#   AGENT_WT_DIRS   space-separated worktree roots to scan
#                   (default: .claude/worktrees .worktrees .agent-worktrees)
#   AGENT_WT_KEEP   space-separated worktree names to always preserve
#
# Exit: 0 audit/reap done · 1 a removal or snapshot failed · 2 bad args / not a repo

set -uo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash rewrites "sha:path" arguments; keep them literal
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

# Untracked paths under these names are regenerable output, not work.
REGEN='node_modules|__pycache__|\.venv|venv|\.pytest_cache|\.ruff_cache|\.mypy_cache|\.next|dist|build|\.turbo|\.cache|coverage|\.tox'

MODE="audit"; ARCHIVE=""; ALL=0; IDLE_H=2; SELFTEST=0
while [ $# -gt 0 ]; do
    case "$1" in
        --reap)    MODE="reap" ;;
        --archive) ARCHIVE="${2:-}"; [ -n "$ARCHIVE" ] || { echo "--archive needs DIR" >&2; exit 2; }; shift ;;
        --all)     ALL=1 ;;
        --min-idle-hours) IDLE_H="${2:-}"; shift ;;
        --self-test) SELFTEST=1 ;;
        -h|--help) sed -n '1,58p' "$0"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
    shift
done
case "$IDLE_H" in ''|*[!0-9]*) echo "--min-idle-hours takes whole hours" >&2; exit 2 ;; esac

# Changed paths that count as work: tracked changes always; untracked ones unless they
# sit under a regenerable directory.
changed_paths() {
    # --no-optional-locks: a plain status REWRITES the index (stat refresh), which bumps the
    # very index mtime last_active reads -- every audit would make a worktree look active.
    git --no-optional-locks -C "$1" status --porcelain 2>/dev/null | while IFS= read -r ln; do
        p="${ln:3}"; p="${p##* -> }"; p="${p#\"}"; p="${p%\"}"
        if [ "${ln:0:2}" = "??" ] && printf '%s\n' "/$p" | grep -Eq "/($REGEN)(/|$)"; then
            continue
        fi
        printf '%s\n' "$p"
    done
}

# Newest activity in a worktree, epoch seconds: git stamps + the changed files.
last_active() {
    local wt="$1" gd newest=0 t f p
    t="$(git -C "$wt" log -g -1 --format=%ct HEAD 2>/dev/null)"; [ -n "$t" ] && newest="$t"
    gd="$(git -C "$wt" rev-parse --absolute-git-dir 2>/dev/null)"
    for f in "$gd/index" "$gd/HEAD"; do
        [ -e "$f" ] || continue
        t="$(stat -c %Y "$f" 2>/dev/null)"
        [ "${t:-0}" -gt "$newest" ] && newest="$t"
    done
    while IFS= read -r p; do
        [ -n "$p" ] || continue
        t="$(find "$wt/$p" -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1)"
        t="${t%.*}"
        [ -n "$t" ] && [ "$t" -gt "$newest" ] && newest="$t"
    done < <(changed_paths "$wt")
    echo "$newest"
}

# Commit tracked + untracked changes into refs/heads/reclaim/<name>, verify, print sha.
# A throwaway index is used, so the worktree's own index and branch are never touched.
snapshot() {
    local wt="$1" n="$2" idx head tree sha bad p
    # inside the git dir: a path git itself printed, valid on Linux, macOS and Git Bash
    idx="$(git -C "$wt" rev-parse --absolute-git-dir)/reaper-index.tmp" || return 1
    rm -f "$idx"
    head="$(git -C "$wt" rev-parse HEAD)" || return 1
    GIT_INDEX_FILE="$idx" git -C "$wt" read-tree HEAD || { rm -f "$idx"; return 1; }
    GIT_INDEX_FILE="$idx" git -C "$wt" add -A -- . \
        ':(exclude,glob)**/node_modules/**' ':(exclude,glob)**/__pycache__/**' \
        ':(exclude,glob)**/.venv/**' ':(exclude,glob)**/.pytest_cache/**' >/dev/null 2>&1 \
        || { rm -f "$idx"; return 1; }
    tree="$(GIT_INDEX_FILE="$idx" git -C "$wt" write-tree)" || { rm -f "$idx"; return 1; }
    sha="$(git -C "$wt" -c user.name=reaper -c user.email=reaper@localhost commit-tree "$tree" -p "$head" \
           -m "reclaim snapshot of $n; restore: git worktree add <dir> reclaim/$n")" || { rm -f "$idx"; return 1; }
    git -C "$wt" update-ref "refs/heads/reclaim/$n" "$sha" || { rm -f "$idx"; return 1; }
    # The working tree must equal the snapshot for every path the throwaway index holds.
    # (Use that index: against the real one, `git diff <sha>` reports untracked as deleted.)
    bad="$(GIT_INDEX_FILE="$idx" git -C "$wt" diff --name-only "$sha" -- . 2>/dev/null | head -1)"
    rm -f "$idx"
    [ -z "$bad" ] || { echo "  snapshot verify failed on $bad" >&2; return 1; }
    while IFS= read -r p; do
        [ -n "$p" ] && [ -e "$wt/$p" ] || continue   # a deletion is recorded by the tree
        [ -n "$(git -C "$wt" ls-tree -r --name-only "$sha" -- "${p%/}")" ] \
            || { echo "  snapshot is missing $p" >&2; return 1; }
    done < <(changed_paths "$wt")
    echo "$sha"
}

if [ "$SELFTEST" = 1 ]; then
    # pwd -W: Git Bash's Windows form, so git.exe can read it (no-op elsewhere)
    T="$(cd "$(mktemp -d)" && { pwd -W 2>/dev/null || pwd; })"; fails=0
    trap 'rm -rf "$T"' EXIT
    ck() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fails=$((fails+1)); fi; }
    old=$(( $(date +%s) - 5*3600 ))
    (
        set -e
        export GIT_COMMITTER_DATE="@$old" GIT_AUTHOR_DATE="@$old"   # reflog stamps 5 h old
        cd "$T"; git init -q main; cd main
        git config user.email t@t; git config user.name t; git config core.autocrlf false
        echo a > a.txt; git add a.txt; git -c core.hooksPath=/dev/null commit -qm a
        git worktree add -q -b w1 .agent-worktrees/w1
        git worktree add -q -b w2 .agent-worktrees/w2
        echo edit >> .agent-worktrees/w1/a.txt
        echo 'x = 1' > .agent-worktrees/w1/new_test.py
        mkdir -p .agent-worktrees/w1/node_modules/p
        echo junk > .agent-worktrees/w1/node_modules/p/big.js
        echo fresh > .agent-worktrees/w2/live.py
    ) >/dev/null 2>&1 || { echo "self-test setup failed"; exit 2; }
    W1="$T/main/.agent-worktrees/w1"; W2="$T/main/.agent-worktrees/w2"
    find "$W1" "$T/main/.git/worktrees/w1" -exec touch -d "@$old" {} + 2>/dev/null
    # w2's git stamps are old too: only its freshly edited file says it is in use (TRAP 3)
    find "$T/main/.git/worktrees/w2" -exec touch -d "@$old" {} + 2>/dev/null
    out="$(cd "$T/main" && AGENT_WT_DIRS=.agent-worktrees bash "$SELF" --reap --all 2>&1)"
    ck "dirty idle worktree removed" "[ ! -d '$W1' ]"
    ck "snapshot ref exists" "git -C '$T/main' rev-parse -q --verify reclaim/w1 >/dev/null"
    ck "UNTRACKED file kept in snapshot (TRAP 2)" "[ -n \"\$(git -C '$T/main' ls-tree -r --name-only reclaim/w1 -- new_test.py)\" ]"
    ck "tracked edit kept in snapshot" "git -C '$T/main' cat-file -p reclaim/w1:a.txt | grep -q edit"
    ck "regenerable dir left out" "[ -z \"\$(git -C '$T/main' ls-tree -r --name-only reclaim/w1 -- node_modules)\" ]"
    ck "recently edited worktree kept (TRAP 3)" "[ -f '$W2/live.py' ]"
    ck "kept one is reported ACTIVE" "printf '%s' \"\$out\" | grep -q 'ACTIVE'"
    [ "$fails" -eq 0 ] && { echo "self-test: ok"; exit 0; }
    echo "self-test: $fails failure(s)"; printf '%s\n' "$out"; exit 1
fi

ROOTS="${AGENT_WT_DIRS:-.claude/worktrees .worktrees .agent-worktrees}"
KEEP="${AGENT_WT_KEEP:-}"

git rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git repo" >&2; exit 2; }

# --- discover -------------------------------------------------------------
FOUND=()
for r in $ROOTS; do
    [ -d "$r" ] || continue
    for d in "$r"/*/; do [ -d "$d" ] && FOUND+=("${d%/}"); done
done

if [ "${#FOUND[@]}" -eq 0 ]; then
    echo "no agent worktrees found under: $ROOTS"
    echo "(registered worktrees: $(git worktree list 2>/dev/null | wc -l))"
    exit 0
fi

echo "found ${#FOUND[@]} worktree(s); git has $(git worktree list 2>/dev/null | wc -l) registered"
echo "  (a mismatch is normal drift — 'git worktree prune' reconciles it)"
echo

# --- audit ----------------------------------------------------------------
SAFE=(); DIRTY=(); now="$(date +%s)"
printf "%-34s %-7s %-9s %-6s %-24s %s\n" NAME DIRTY UNPUSHED IDLE_H BRANCH VERDICT
for d in "${FOUND[@]}"; do
    n="$(basename "$d")"
    dirty="$(changed_paths "$d" | wc -l)"
    # HEAD, not --branches. See TRAP 1.
    unpushed="$(git -C "$d" log HEAD --not --remotes --oneline 2>/dev/null | wc -l)"
    br="$(git -C "$d" rev-parse --abbrev-ref HEAD 2>/dev/null)"
    idle=$(( (now - $(last_active "$d")) / 3600 ))

    case " $KEEP " in
        *" $n "*) v="KEEP(pinned)" ;;
        *)  if [ "$idle" -lt "$IDLE_H" ]; then v="ACTIVE(<${IDLE_H}h)"
            elif [ "${dirty:-0}" -eq 0 ] && [ "${unpushed:-0}" -eq 0 ]; then v="SAFE"; SAFE+=("$d")
            else v="DIRTY"; DIRTY+=("$d"); fi ;;
    esac
    printf "%-34s %-7s %-9s %-6s %-24s %s\n" "$n" "${dirty:-?}" "${unpushed:-?}" "$idle" "${br:0:24}" "$v"
done
echo
echo "safe=${#SAFE[@]}  dirty=${#DIRTY[@]}  (ACTIVE and pinned ones are never touched)"

# --- archive (an optional extra copy outside the repo) ----------------------
if [ -n "$ARCHIVE" ] && [ "${#DIRTY[@]}" -gt 0 ]; then
    mkdir -p "$ARCHIVE" || exit 1
    for d in "${DIRTY[@]}"; do
        n="$(basename "$d")"
        git --no-optional-locks -C "$d" status --porcelain > "$ARCHIVE/$n.status.txt" 2>/dev/null
        git -C "$d" log HEAD --not --remotes --patch > "$ARCHIVE/$n.unpushed.patch" 2>/dev/null
    done
    echo ">>> wrote status + unpushed patches for ${#DIRTY[@]} worktree(s) to $ARCHIVE"
fi

# --- reap -----------------------------------------------------------------
[ "$MODE" = "reap" ] || exit 0
TARGETS=("${SAFE[@]}")
[ "$ALL" = 1 ] && TARGETS+=("${DIRTY[@]}")
[ "${#TARGETS[@]}" -eq 0 ] && { echo "nothing to reap"; exit 0; }

echo ">>> reaping ${#TARGETS[@]} worktree(s) — I/O heavy; hundreds of GB take many minutes."
ok=0; failed=0
for d in "${TARGETS[@]}"; do
    n="$(basename "$d")"
    if [ "$(changed_paths "$d" | wc -l)" -gt 0 ]; then
        if ! sha="$(snapshot "$d" "$n")"; then
            echo "  KEPT $n: snapshot failed, nothing removed" >&2; failed=$((failed+1)); continue
        fi
        [ -n "$ARCHIVE" ] && git -C "$d" diff --binary HEAD "$sha" > "$ARCHIVE/$n.snapshot.patch" 2>/dev/null
        echo "  snapshot $n -> reclaim/$n ${sha:0:11}"
    fi
    # `git worktree remove` also drops the registration; rm -rf alone leaves a stale entry.
    if git worktree remove --force "$d" 2>/dev/null && [ ! -e "$d" ]; then
        ok=$((ok+1)); echo "  reaped ($ok/${#TARGETS[@]}): $n"
    else
        failed=$((failed+1)); echo "  FAILED: $n (files in use?) — its snapshot, if any, is kept" >&2
    fi
done
git worktree prune 2>/dev/null
echo ">>> reaped $ok, failed $failed; registrations pruned."
echo "    restore any snapshotted one with: git worktree add <dir> reclaim/<name>"
[ "$failed" -eq 0 ]
