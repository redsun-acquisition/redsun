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

Write what changed in plain words, so someone who hasn't seen the diff
understands it.

## Issues

An issue title takes the same form as a commit's first line and names the
change it asks for: `fix: log files stay open after shutdown`,
`feat: add a toolbar placement`. The issue templates start the title for
you.

## Pull requests

Open the pull request against `main`. Its title follows the same rules as a
commit's first line, because the changelog entry is made from it:
`feat(session): add strict sessions` is listed under *Added* as "Add strict
sessions".

The description is a list of one-line bullets in the imperative, one per
change a reviewer can see, with no headers:

```markdown
- Add `strict` to the session file
- Stop a session whose component fails to build when `strict` is set
- Rename `MyMotor.go` to `MyMotor.move`, which existing code must follow
```

A change that existing code must follow says so in its bullet. Leave out tests,
coverage and the checks you ran: CI reports them on the pull request.

## Labels

Every pull request needs one label saying which changelog section it goes in,
and CI refuses a pull request without one.

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
