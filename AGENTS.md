# AGENTS

## Release Version Policy (Required)

- Every releaseable change must bump `project.version` in `pyproject.toml`.
- Use semantic versioning and default to patch bumps (`x.y.z -> x.y.(z+1)`) unless the change is explicitly minor/major.
- After changing the version, run `uv lock` so `uv.lock` reflects the same version.
- Add a short changelog entry in `CHANGELOG.md` describing the bump reason.

Rationale: this avoids stale `uv tool install` cache behavior and ensures users receive the latest build.
