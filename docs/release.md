# Release procedure

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

# 4. Run tests
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
```

## Checklist

Every release MUST complete all steps in order:

- [ ] Version bumped in `pyproject.toml`
- [ ] `uv.lock` updated (`uv lock`)
- [ ] `LOG.md` updated
- [ ] Tests pass (`uv run pytest`)
- [ ] Commit created
- [ ] Git tag created (`git tag vX.Y.Z`)
- [ ] Pushed to GitHub with tags (`git push origin main --tags`)
- [ ] GitHub release created with notes (`gh release create`)
- [ ] Built and published to PyPI (`uv build && twine upload`)
