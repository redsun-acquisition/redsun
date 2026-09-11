---
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git add:*), Bash(git log:*)
description: Stage a change and suggest a conventional commit message
---

Current state:
- Status: !`git status --short`
- Staged: !`git diff --staged --stat`
- Unstaged: !`git diff --stat`
- Recent style: !`git log --oneline -10`

Stage the files relevant to this change, then print a conventional-commit
message for it and stop. **Never run `git commit`, `git push`, or any command
that rewrites history.** The commit is the user's to make.

The message uses a type matching the style above (`feat:`, `fix:`, `test:`,
`docs:`, `build:`, `refactor:`, `chore:`). One imperative line, lowercase after
the colon, no trailing period.

**The subject line on its own is the default, and is enough for nearly every
commit.** Write a body only when a reader could not recover the point from the
diff: a `BREAKING CHANGE:` footer and what callers must change, a constraint
that forced an approach the diff makes look arbitrary, or a measurement that
motivated the change. Never use the body to restate the diff, to explain the
convention or principle being applied, or to argue that the change is a good
idea. When unsure, leave it out.

Small, focused commits: if the working tree holds unrelated changes, stage only
the coherent slice and say what you left behind. Where one file carries two
concerns, say so rather than staging it into the wrong slice.

No co-author trailers, no emoji.
