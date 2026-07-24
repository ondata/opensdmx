---
name: release
description: Release opensdmx (patch subrelease or normal release) following docs/release.md exactly — bump version, lock, lint, test, tag, push, GitHub release, PyPI publish. User-only; run it when cutting a new version.
disable-model-invocation: true
---

# Release opensdmx

Cut a new opensdmx version by following `docs/release.md` step by step. `docs/release.md` is the source of truth — if it ever diverges from this file, the doc wins; read it first.

## Critical rule (do not skip)

The version bump lives in a **dedicated commit on `main`, made AFTER the PR is merged** — never inside the feature PR. Sequence is always: merge the PR into `main` → `git switch main && git pull` → then run the bump commit here.

## Pick the release type

- **Subrelease (patch)** — low-risk patch that does not change the release flow: bug fix, small CLI UX correction, docs-only follow-up. Bump only the patch: `0.5.0 → 0.5.1`, `1.2.3 → 1.2.4`.
- **Normal release** — everything else (new features, behaviour changes). Bump minor/major as appropriate.

Both types run the **same steps below**; only the version bump differs.

## Preconditions (verify before touching anything)

- On `main`, up to date, and the feature PR is already merged (`git switch main && git pull`).
- Working tree clean (`git status`).
- `gh` CLI authenticated.
- PyPI credentials configured for `twine` (token in `~/.pypirc` or env).

## Steps (run in order — all must pass)

Substitute `X.Y.Z` with the new version everywhere.

1. Bump `version = "X.Y.Z"` in `pyproject.toml`.

2. Refresh the lockfile:

   ```bash
   uv lock
   ```

3. Update `LOG.md` with the release notes (English, most recent entry on top, `YYYY-MM-DD` heading).

4. Run the linter and the full test suite — **both must pass before any publish step**. Stop the release if either fails:

   ```bash
   uv run ruff check src/
   uv run pytest tests/ -v
   ```

5. Commit and tag:

   ```bash
   git add -u
   git commit -m "chore: bump version to vX.Y.Z"
   git tag vX.Y.Z
   ```

6. **Confirm with the user before this point** — steps 6–8 are outward-facing and hard to reverse. Push branch and tag:

   ```bash
   git push origin main --tags
   ```

7. Create the GitHub release (notes in English):

   ```bash
   gh release create vX.Y.Z --title "vX.Y.Z" --notes "release notes here"
   ```

8. Build and publish to PyPI:

   ```bash
   uv build
   twine upload dist/opensdmx-X.Y.Z*
   ```

9. Refresh the local CLI install:

   ```bash
   uv tool install --editable .
   ```

## Checklist (every release MUST complete all, in order)

- [ ] PR merged into `main`, local `main` pulled and clean
- [ ] Version bumped in `pyproject.toml`
- [ ] `uv.lock` updated (`uv lock`)
- [ ] `LOG.md` updated
- [ ] Linter passes (`uv run ruff check src/`)
- [ ] Tests pass (`uv run pytest`)
- [ ] Commit + git tag created (`git tag vX.Y.Z`)
- [ ] Pushed with tags (`git push origin main --tags`)
- [ ] GitHub release created with notes
- [ ] Built and published to PyPI (`uv build && twine upload`)
- [ ] Local CLI updated (`uv tool install --editable .`)
