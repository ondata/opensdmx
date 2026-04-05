---
name: release
description: >
  Guides and executes the full opensdmx release procedure: version bump,
  lock file update, LOG.md update, tests, commit, tag, push, GitHub release,
  and PyPI publish. Use this skill whenever the user says "release", "nuova
  release", "publish", "bump version", "rilascio", or anything that implies
  shipping a new version of opensdmx to PyPI or GitHub. Also trigger when
  the user asks to go through the release checklist in docs/release.md.
license: MIT
---

# opensdmx Release Skill

This skill guides you through the 8-step release procedure defined in
`docs/release.md`. Execute each step in order. For steps that modify shared
state (push, publish), always confirm with the user before proceeding.

## Before you start

Read the current state:

```bash
grep "^version" pyproject.toml          # current version
git log --oneline -5                    # recent commits (for release notes)
git status                              # make sure working tree is clean
head -20 LOG.md                         # what changed since last release
```

Ask the user what the new version should be if they haven't said. Follow
semver: patch (0.3.x) for fixes and small features, minor (0.x.0) for new
commands or significant new behaviour.

---

## Step 1 — Bump version in pyproject.toml

Edit `pyproject.toml`: change `version = "X.Y.Z"` to the new version.
Then verify:

```bash
grep "^version" pyproject.toml
```

## Step 2 — Update uv.lock

```bash
uv lock
```

Confirm the lock file updated cleanly (no errors).

## Step 3 — Update LOG.md

Add a new heading at the top of `LOG.md` with today's date in `YYYY-MM-DD`
format. List the changes as short bullet points — one per meaningful change.
Draw from git log since the last tag and from what the user described in the
current conversation.

Format:

```
## YYYY-MM-DD

- feat: <what was added>
- fix: <what was fixed>
- docs: <what was documented>
```

## Step 4 — Run tests

```bash
uv run pytest tests/ -v
```

All tests must pass before proceeding. If any fail, stop here and fix them.

## Step 5 — Commit and tag

**Confirm with the user before running this step.**

```bash
git add pyproject.toml uv.lock LOG.md src/ skills/
git commit -m "chore: bump version to vX.Y.Z"
git tag vX.Y.Z
```

Replace `X.Y.Z` with the new version. Adjust the staged files to include
only what actually changed.

## Step 6 — Push with tags

**Confirm with the user before running this step.**

```bash
git push origin main --tags
```

## Step 7 — Create GitHub release

**Confirm with the user before running this step.**

Read the LOG.md entries for the new version and generate the release notes
automatically. Group changes by type (features, fixes, docs). Remove
internal/implementation details — keep only what's meaningful for users
of the CLI.

```bash
gh release create vX.Y.Z --title "vX.Y.Z" --notes "$(cat <<'EOF'
## What's new

### Features
- ...

### Fixes
- ...
EOF
)"
```

Show the generated notes to the user before running the command so they can
correct anything, but do not ask for approval unless they want to change something.

## Step 8 — Build and publish to PyPI

**Confirm with the user before running this step.**

```bash
uv build
twine upload dist/opensdmx-X.Y.Z*
```

Verify the upload succeeded by checking the PyPI URL printed by twine.

---

## Checklist (track as you go)

- [ ] Version bumped in `pyproject.toml`
- [ ] `uv.lock` updated
- [ ] `LOG.md` updated
- [ ] Tests pass
- [ ] Commit created with tag
- [ ] Pushed to GitHub with tags
- [ ] GitHub release created
- [ ] Built and published to PyPI

---

## Notes

- If the working tree has uncommitted changes at the start, ask the user
  whether to include them in this release or stash them first.
- If tests fail, do not proceed past step 4. Fix the root cause.
- Steps 6–8 are irreversible (push, public release, PyPI publish) —
  always confirm explicitly before each one.
- Use `gh release create --draft` if the user wants to review the release
  page before making it public.
