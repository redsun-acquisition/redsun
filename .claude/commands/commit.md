---
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git add:*), Bash(git commit:*), Bash(git log:*)
description: Stage and commit with a conventional commit message
---

Current state:
- Status: !`git status --short`
- Staged: !`git diff --staged --stat`
- Unstaged: !`git diff --stat`
- Recent style: !`git log --oneline -10`

Stage the files relevant to this change and commit with a conventional-commit
message matching the style above (`feat:`, `fix:`, `test:`, `docs:`, `build:`,
`refactor:`, `chore:`). One imperative line, lowercase after the colon, no
trailing period. Add a body only for breaking changes or non-obvious rationale
— say *why*, not *what*.

Small, focused commits: if the working tree contains unrelated changes, commit
only the coherent slice and say what you left behind.

Do not push. No co-author trailers, no emoji.
