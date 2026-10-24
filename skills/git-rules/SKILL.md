---
name: git-rules
description: >
  The user's personal rules for git and GitHub repositories. Activate BEFORE
  acting whenever the work touches a repository's commits, branches, pull
  requests or GitHub settings: committing changes ("commit this", "commit the
  work"), creating or deleting a branch, opening, merging or closing a PR, cleaning up after a merge, the user confirming a feature works or passed testing (it then gets merged), creating a new GitHub repo, pushing session
  notes (SESSION.md, CLAUDE.md), or changing repo settings. Also activate when
  the user states a new git/GitHub habit or says "remember this rule", "add
  this to my git rules", "make it a rule for all my repos" — new rules are
  saved in this skill, not in CLAUDE.md. Git feels doable without a skill;
  load this one anyway, because these are the user's own choices and can't be
  guessed. Not for explaining how git works in general.
---

# Git and GitHub rules

These are the user's standing rules for every repository they own. They apply in all projects. A project's own `CLAUDE.md` wins where it says something different.

"The user's repos" means the repos owned by the logged-in GitHub account (`gh api user --jq .login`).

## Rules

### 1. A branch is deleted as soon as its PR is merged

One branch exists per open PR. Once the PR is merged the branch has no further job, and leaving it would let branches pile up as PRs do. Nothing is lost: the commits are in the default branch, the PR page keeps the discussion and diff, and GitHub offers "Restore branch" there.

After a merge:

1. Confirm the branch's tip is in the default branch (`git merge-base --is-ancestor origin/<branch> origin/<default>`). Stop if it isn't.
2. Switch to the default branch and bring it up to date.
3. Delete the local branch with `git branch -d <branch>` (lowercase `-d`, which refuses an unmerged branch).
4. Delete the GitHub copy if it is still there: `git push origin --delete <branch>`.
5. `git fetch --prune`.

When merging from the CLI, `gh pr merge <n> --merge --delete-branch` covers steps 2–4.

Leave a branch alone when its PR is still open, or when the PR was closed without merging: that work exists nowhere else. Permanent branches (the default branch, release branches) are never deleted.

### 2. Every repo has "Automatically delete head branches" turned on

This makes GitHub remove its copy of a branch when the PR is merged. Only the GitHub copy goes; the local copy is still deleted by hand, as in rule 1.

GitHub has no account-wide default for this setting, so a newly created repo starts with it off. Turn it on right after creating a repo:

```bash
gh api -X PATCH repos/<owner>/<repo> -F delete_branch_on_merge=true
```

To check or repair all repos at once:

```bash
# list any repo that has it off
gh repo list --limit 200 --json nameWithOwner,deleteBranchOnMerge \
  --jq '.[] | select(.deleteBranchOnMerge | not) | .nameWithOwner'

# turn it on everywhere
for r in $(gh repo list --limit 200 --json nameWithOwner --jq '.[].nameWithOwner'); do
  gh api -X PATCH "repos/$r" -F delete_branch_on_merge=true --silent
done
```

### 3. Session notes are committed and pushed with the work

Session logs and agent memory files kept in a repo's root (`SESSION.md`, `CLAUDE.md`, …) are committed and pushed along with the work, never left as uncommitted changes. Unattended tasks stop without committing when they find uncommitted work in a repo that they didn't make, so a dirty notes file blocks them.

Before pushing, read the diff and leave out anything sensitive (secrets, tokens, credentials, personal data), especially in public repos. Skip a notes file only when another live session is clearly still writing it.

### 4. A request to commit is also a request to push

When the user asks for a commit, push it to the remote in the same step, without asking first. A commit that stays local is not backed up and does not reach the user's other machines.

```bash
git push                      # the branch already tracks a remote branch
git push -u origin <branch>   # first push of a new branch
```

Push only the current branch, and never force-push under this rule. If the push is rejected (the remote has commits the local branch lacks) or fails, stop and report it; don't rebase, merge or force on your own.

Don't push when the user says so ("commit only", "don't push"), when the repo has no remote, or when the task's own instructions forbid pushing (an unattended worker told to commit but never push).

### 5. A feature that has passed its test is merged into the default branch, and its branch deleted

Once the user has tried a feature and says it works ("great", "it works", "passed"), it goes into the default branch right away, without asking first. A finished feature left on a side branch is easy to forget, and the next piece of work then starts from a default branch that lacks it.

1. Commit and push what's left on the branch (rule 4).
2. Open a PR into the default branch if none is open, then merge it and delete the branch (rule 1):

```bash
gh pr create --base <default> --head <branch> --title "…" --body "…"
gh pr merge <n> --merge --delete-branch
git fetch --prune
git merge-base --is-ancestor <last commit> origin/<default> && echo merged
```

If the repo has no GitHub remote, merge locally (`git switch <default> && git merge --no-ff <branch>`), push, then `git branch -d <branch>`.

This needs the user's own test: passing checks or a build are not enough. It does not apply when the PR can't merge cleanly (stop and report the conflict), when the user says to hold it, when the project's `CLAUDE.md` holds that PR for the user's OK, or to PRs opened by unattended tasks the user hasn't tried. If the branch also carries other unmerged work, say so before merging, since that work goes in too.

## Adding or changing a rule

When the user states a new git or GitHub habit, or asks to remember one, it goes here rather than into a `CLAUDE.md`, so it follows the user to every machine where this skill is installed.

1. Find the skill's source: `readlink -f ~/.claude/skills/git-rules/SKILL.md` gives the file inside the user's skills repository. Edit that file, not a copy.
2. Add a numbered section under "Rules": the rule in one sentence as the heading, then why the user wants it, then the exact commands. Say when the rule does not apply.
3. If the rule needs a setting changed on existing repos, apply it now and report how many repos changed.
4. Commit and push the skills repository, so other machines get the rule on their next pull.
