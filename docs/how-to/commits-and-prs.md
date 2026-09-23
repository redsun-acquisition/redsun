---
icon: lucide/git-pull-request
---

# How to write commits and pull requests

## Commit messages

The first line follows [Conventional Commits](https://www.conventionalcommits.org):

```
type(scope): summary
```

- `type` is one of `feat`, `fix`, `docs`, `refactor`, `test`, `ci`, `chore`.
  Add `!` after it for a change that breaks existing code: `feat!: ...`.
- `scope` is optional and names the part changed: `session`, `qt`, `log`.
- The summary is in the imperative ("add", "fix", "move"), with no full stop,
  and the whole line is 72 characters or fewer.

A commit that does several things gets a body of short bullets, each one
imperative:

```
refactor(session): read each session file once

- merge the sources before validating them
- log the files in the order they are layered
```

Write what changed in plain words, so someone who has not seen the diff
understands it.

## Issues

An issue title follows the same form as a commit's first line, naming the
change it asks for: `fix: log files stay open after shutdown`,
`feat: add a toolbar placement`. The issue templates start the title for
you.

## Pull requests

Open the pull request against `main`. The title follows the same rules as a
commit's first line, since it becomes the changelog entry.

Split the description into the sections that apply:

- `## Summary`: what the pull request does, in a line or two.
- `## Changes`: one short bullet per change.
- `## Breaking changes`: what existing code must change, if anything.
- `## Testing`: the checks you ran and their result.

## Labels

Every pull request needs one label saying which changelog section it goes in.
CI refuses a pull request without one.

| label | changelog section |
| --- | --- |
| `added` | Added |
| `changed` | Changed |
| `deprecated` | Deprecated |
| `removed` | Removed |
| `fixed` | Fixed |
| `security` | Security |
| `skip-changelog` | none: tests, CI, refactors nobody using `redsun` would notice |

Add `breaking` as well when existing code has to change. The entry is then
marked **Breaking**.
