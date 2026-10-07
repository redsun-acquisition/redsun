---
icon: lucide/package
---

# How to make a release

A release starts with the changelog, which a script writes from the pull
requests merged since the last release, grouped by their
[labels](commits-and-prs.md#labels). Don't edit it by hand.

## Prerequisites

`gh` signed in with access to the repository, and a clone of it.

## 1. Write the changelog section

On an up-to-date `main`, make a release branch and write the section, with
the version without its `v`:

```bash
git switch main
git pull
git switch -c release/v0.14.1
uv run python scripts/release_notes.py prepare 0.14.1
```

The script asks GitHub for the pull requests merged since the last final
release, and writes a section for them at the top of
`docs/reference/changelog.md`, with the date and a compare link.

Read the section. If a title reads badly, rename the pull request it came
from, so the changelog and GitHub agree. Then discard the
section with `git checkout docs/reference/changelog.md` and run the script
again.

## 2. Open the pull request and merge it

```bash
git commit -am "docs: add the 0.14.1 changelog"
git push origin release/v0.14.1
gh pr create --base main --label skip-changelog \
  --title "docs: add the 0.14.1 changelog" \
  --body "Adds the changelog section for 0.14.1."
```

The checks start as on any pull request. Merge it once they pass.

## 3. Tag

Tag the merge commit and push the tag:

```bash
git switch main
git pull
git tag v0.14.1
git push origin v0.14.1
```

The tag publishes the package to PyPI and the docs, and creates the GitHub
release, whose notes are the changelog section.

!!! warning "A final-release tag without a changelog section"

    If the tag's version has no section, the package build fails with a
    message naming the `prepare` command, and neither PyPI nor the GitHub
    release gets anything. Merge the changelog pull request (steps 1 and 2)
    before you tag.

## Release candidates

Tag a candidate `v0.14.1rc1` without preparing anything. It publishes the
package, but no GitHub release and no changelog section: the final release's
section lists every pull request since the previous final release.
