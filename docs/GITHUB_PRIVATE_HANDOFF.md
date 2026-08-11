# Private GitHub Handoff

This checklist prepares a private repository upload but intentionally stops
before any remote mutation. The confirmed display name is `ChaosAtlas` and the
proposed repository slug is `chaos-atlas`; the owner must still confirm the
exact organization/account and URL before upload.

## Local Review Before Approval

- [ ] `README.md` and `docs/` accurately describe the current evidence.
- [ ] `git diff --stat` and `git status --short` have been reviewed; unrelated
      user changes are preserved.
- [ ] No credentials, tokens, private endpoints, unredacted Secrets, or raw
      sensitive logs are present.
- [ ] Large archives and generated binaries are intentionally ignored or have a
      paper-reproducibility reason to be included.
- [ ] Knowledge-base validators pass for all included project card sets.
- [ ] Focused tests pass; any environment-blocked runtime checks are documented.
- [ ] Third-party licenses and nested source checkout rules are understood.

## Explicit Approval Required

Before upload, confirm all of the following in one message:

1. the final display name and slug;
2. the GitHub account/organization and exact private remote URL;
3. the branch to publish;
4. whether the current dirty experiment artifacts should be included;
5. permission to run `git remote add` and `git push` (or the approved GitHub CLI equivalent).

Until then, do not configure a remote, authenticate, create a repository, or
push data. A private repository is still an external copy and must pass the
same sensitive-data review as a public release.

## Suggested First Upload Shape

Keep the initial upload local and reviewable:

```text
README.md
docs/
governance/
raw_yaml/
artifacts/
reporting/
tools/
task_plan.md
findings.md
progress.md
```

The exact inclusion of nested source checkouts, `chaos-mesh-*.tgz`, temporary
directories, and generated logs must be decided from the final diff, not by a
blanket `git add .`.
