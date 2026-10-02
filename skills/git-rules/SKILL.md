---
name: git-rules
description: >
  The user's personal rules for git and GitHub repositories. Activate BEFORE
  acting whenever the work touches a repository's branches, pull requests or
  GitHub settings: creating or deleting a branch, opening, merging or closing a
  PR, cleaning up after a merge, creating a new GitHub repo, pushing session
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

## Adding or changing a rule

When the user states a new git or GitHub habit, or asks to remember one, it goes here rather than into a `CLAUDE.md`, so it follows the user to every machine where this skill is installed.

1. Find the skill's source: `readlink -f ~/.claude/skills/git-rules/SKILL.md` gives the file inside the user's skills repository. Edit that file, not a copy.
2. Add a numbered section under "Rules": the rule in one sentence as the heading, then why the user wants it, then the exact commands. Say when the rule does not apply.
3. If the rule needs a setting changed on existing repos, apply it now and report how many repos changed.
4. Commit and push the skills repository, so other machines get the rule on their next pull.
