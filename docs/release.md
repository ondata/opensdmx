# Release procedure

## Prerequisites

- PyPI credentials configured for `twine` (token in `~/.pypirc` or env)
- `gh` CLI authenticated

## Steps

```bash
# 1. Bump version in pyproject.toml
#    Edit version = "X.Y.Z" → "X.Y.Z+1"

# 2. Run tests
uv run pytest tests/ -v

# 3. Commit and tag
git add -u
git commit -m "chore: bump version to vX.Y.Z"
git tag vX.Y.Z

# 4. Push with tags
git push origin main --tags

# 5. Create GitHub release
gh release create vX.Y.Z --title "vX.Y.Z" --notes "release notes here"

# 6. Build and publish to PyPI
uv build
uv run twine upload dist/opensdmx-X.Y.Z*
```

## Checklist

- [ ] Version bumped in `pyproject.toml`
- [ ] Tests pass
- [ ] `LOG.md` updated
- [ ] Commit + tag created
- [ ] Pushed to GitHub
- [ ] GitHub release created with notes
- [ ] Published to PyPI
