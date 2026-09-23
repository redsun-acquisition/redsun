# Make a release

The changelog is written from the pull requests merged since the last
release, grouped by their [labels](commits-and-prs.md#labels). Nobody edits
it by hand.

## 1. Prepare the release

On GitHub, run the **Prepare Release** workflow from the Actions tab, with the
version without its `v`, such as `0.14.0`. It:

1. asks GitHub for the pull requests merged since the last final release;
2. writes a section for them at the top of `docs/reference/changelog.md`, with
   the date and a compare link;
3. opens a pull request with that change, on the branch `release/v0.14.0`.

A pull request opened by a workflow does not start the other checks. Close
and reopen it to start them.

## 2. Review and merge

Read the new section. A title that reads badly is fixed by renaming the pull
request it came from and running the workflow again, so the changelog and
GitHub agree. Then merge.

## 3. Tag

Tag the merge commit and push the tag:

```bash
git switch main
git pull
git tag v0.14.0
git push origin v0.14.0
```

The tag publishes the package to PyPI and the docs, and creates the GitHub
release, whose notes are the changelog section.

## Release candidates

Tag a candidate `v0.14.0rc1` without preparing anything. It publishes the
package, but no GitHub release and no changelog section: the final release's
section lists every pull request since the previous final release.
