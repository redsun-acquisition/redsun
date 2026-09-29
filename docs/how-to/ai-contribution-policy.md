---
icon: lucide/bot
---

# AI contribution policy

!!! note

    This document is mirrored from the zarr-python AI contribution policy:
    [AI-assisted contributions](https://zarr.readthedocs.io/en/main/contributing/#ai-assisted-contributions).

AI coding tools are increasingly common in open source development. These tools are welcome in Zarr-Python, but the same standards apply to all contributions regardless of how they were produced — whether written by hand, with AI assistance, or generated entirely by an AI tool.

## You are responsible for your changes

If you submit a pull request, you are responsible for understanding and having fully reviewed the changes. You must be able to explain why each change is correct and how it fits into the project.

## Communication must be your own

PR descriptions, issue comments, and review responses must be in your own words. The substance and reasoning must come from you. Using AI to polish grammar or phrasing is fine, but do not paste AI-generated text as comments or review responses.

## Review every line

You must have personally reviewed and understood all changes before submitting. If you used AI to generate code, you are expected to have read it critically and tested it. The PR description should explain the approach and reasoning — do not leave it to reviewers to figure out what the code does and why.

## Keep PRs reviewable

Generating code with AI is fast; reviewing it is not. A large diff shifts the burden from the contributor to the reviewer. PRs that cannot be reviewed in reasonable time with reasonable effort may be closed, regardless of their potential usefulness or correctness. Use AI tools not only to write code but to prepare better, more reviewable PRs — well-structured commits, clear descriptions, and minimal scope.

If you are planning a large AI-assisted contribution (e.g., a significant refactor or a new subsystem), **open an issue first** to discuss the scope and approach with maintainers. Maintainers may also request that large changes be broken into smaller, reviewable pieces.

## Documentation

The same principles apply to documentation. Zarr has domain-specific semantics (chunked storage, codec pipelines, Zarr v2/v3 format details) that AI tools frequently get wrong. Do not submit documentation that you haven't carefully read and verified.
