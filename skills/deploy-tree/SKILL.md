---
name: deploy-tree
description: >-
  A deploy tree is a checkout that containers or a sync lane serve (in AitherOS: C:\AitherOS-Fresh). Never edit files in it. Make changes in an awgit worktree and merge them; the sync lane moves the deploy tree. Use when a Write/Edit is refused with "is a deploy tree", when a deploy is "stuck behind uncommitted edits", or when you need to recover a rescued file.
---

# deploy-tree — served, never edited

A **deploy tree** is a checkout something serves: containers bind-mount it, an editable
install runs from it, and a sync lane moves it to the branch tip after every merge.
Edits made there are never committed and block the next deploy.

## Make a change

```bash
awgit wt new my-fix --sparse <dirs you need>   # isolated worktree off develop
# edit, test, commit there; open a PR to develop
```

It goes live when it merges: the sync lane moves the deploy tree.

## Why your Write/Edit was refused

The tree's git config has `awgit.deploytree=true`, and the PreToolUse hook
`awgit deploy-tree guard` denies Edit / Write / MultiEdit / NotebookEdit inside it.
Linked worktrees nested under it are separate checkouts and are not refused.
`AWGIT_ALLOW_DEPLOY_TREE_EDIT=1` exists for a deliberate hand fix only.

## Operate it

```bash
awgit deploy-tree mark --repo <tree>      # opt a checkout in (unmark to opt out)
awgit deploy-tree status --repo <tree>    # marked? how many uncommitted files, by top dir
```

Your deploy sync lane moves the tree to the branch tip. The AitherOS lane carries uncommitted edits that merge cleanly. Anything else it commits to a
pushed `rescue/deploy-tree/<ts>` branch, announces on the relay, and then moves on.
`SYNC_DEPLOY_RESCUE=0` restores the old refuse-and-stop behaviour.

## Recover a rescued file

```bash
git fetch origin 'rescue/deploy-tree/*:refs/remotes/origin/rescue/deploy-tree/*'
git checkout origin/rescue/deploy-tree/<ts> -- <path>   # in YOUR worktree, then commit
```

Law: awknowledge law 31, "A deploy tree is served, never edited".
