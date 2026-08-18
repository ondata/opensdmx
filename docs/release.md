# Release procedure

## Subrelease

Use a subrelease for a low-risk patch that does not change the release flow,
for example a bug fix, a small CLI UX correction, or a docs-only follow-up
that should ship as the next patch version.

Patch-version pattern:

- `0.5.0` -> `0.5.1`
- `1.2.3` -> `1.2.4`

Minimal subrelease workflow:

```bash
# 1. Bump only the patch version in pyproject.toml

# 2. Refresh lockfile
uv lock

# 3. Update LOG.md with the patch notes

# 4. Run linter and full test suite — both must pass before any publish step
uv run ruff check src/
uv run pytest tests/ -v

# 5. Commit and tag the patch release
git add -u
git commit -m "chore: bump version to vX.Y.Z"
git tag vX.Y.Z

# 6. Push branch and tag
git push origin main --tags

# 7. Publish the release artifacts
gh release create vX.Y.Z --title "vX.Y.Z" --notes "patch release notes here"
uv build
twine upload dist/opensdmx-X.Y.Z*

# 8. Verify the published artifact (see step 9 of the full procedure — a green
#    test suite does not prove the package is installable)
uvx --refresh --from opensdmx==X.Y.Z opensdmx --version

# 9. Refresh the local CLI install
uv tool install --editable .
```

## Prerequisites

- PyPI credentials configured for `twine` (token in `~/.pypirc` or env)
- `gh` CLI authenticated

## Steps

```bash
# 1. Bump version in pyproject.toml
#    Edit version = "X.Y.Z" → "X.Y.Z+1"

# 2. Update uv.lock
uv lock

# 3. Update LOG.md with changes

# 4. Run linter and full test suite — both must pass before any publish step
uv run ruff check src/
uv run pytest tests/ -v

# 5. Commit and tag
git add -u
git commit -m "chore: bump version to vX.Y.Z"
git tag vX.Y.Z

# 6. Push with tags
git push origin main --tags

# 7. Create GitHub release
gh release create vX.Y.Z --title "vX.Y.Z" --notes "release notes here"

# 8. Build and publish to PyPI
uv build
twine upload dist/opensdmx-X.Y.Z*

# 9. Verify the PUBLISHED artifact, not the local source. `uvx` resolves and
#    installs from PyPI into a throwaway environment, so this is what a new
#    user gets. The lock file proves nothing here: a dependency the code
#    imports but never declares (it only arrived transitively) installs fine
#    locally and breaks for everyone else. `--refresh` skips a stale index
#    cache — right after upload the version may not resolve on the first try.
uvx --refresh --from opensdmx==X.Y.Z opensdmx --version
uvx --from opensdmx==X.Y.Z opensdmx providers   # a real command, not just --version

# 10. Update local CLI
uv tool install --editable .
```

## Checklist

Every release MUST complete all steps in order:

- [ ] Version bumped in `pyproject.toml`
- [ ] `uv.lock` updated (`uv lock`)
- [ ] `LOG.md` updated
- [ ] Linter passes (`uv run ruff check src/`)
- [ ] Tests pass (`uv run pytest`)
- [ ] Commit created
- [ ] Git tag created (`git tag vX.Y.Z`)
- [ ] Pushed to GitHub with tags (`git push origin main --tags`)
- [ ] GitHub release created with notes (`gh release create`)
- [ ] Built and published to PyPI (`uv build && twine upload`)
- [ ] Published artifact resolved from PyPI and run (`uvx --refresh --from opensdmx==X.Y.Z opensdmx --version`, plus one real command)
- [ ] Local CLI updated (`uv tool install --editable .`)
