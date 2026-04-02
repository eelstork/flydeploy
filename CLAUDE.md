# flydeploy

## Versioning

When adding or changing public functions, bump the version in
`pyproject.toml` before pushing. Deploy scripts install flydeploy
via `pip install --upgrade git+...` — pip compares the version string
to decide whether to reinstall. If the version is unchanged, pip
skips the upgrade and callers won't see new code.

Use semver: bump the minor version for new features (0.2.0 → 0.3.0),
patch for bug fixes (0.2.0 → 0.2.1).
