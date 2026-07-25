---
allowed-tools: Bash(git:*), Bash(gh:*)
description: Push the current branch and open a PR
---

- Branch: !`git rev-parse --abbrev-ref HEAD`
- Commits vs main: !`git log main..HEAD --oneline`
- Diff stat: !`git diff main...HEAD --stat`

Push the branch with `-u`, then open a PR with `gh pr create`.

Title: conventional-commit style, summarising the branch as a whole.

Body:
```
## Summary
- 3 bullets max, what changed and why

## Testing
- commands run and their result
```

If the work resolves issues, add one `Fixes #NNN` line per issue so GitHub
auto-closes them on merge.

Verify the body landed by reading it back with `gh pr view --json body`.
No emoji. Do not merge.
