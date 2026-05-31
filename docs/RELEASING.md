# Release Process

This document describes how to publish pre-releases and final releases for `casambi-bt-hass`.

---

## Version Numbering

Versions follow [PEP 440](https://peps.python.org/pep-0440/) and must be valid for both Python packaging and HACS:

| Stage | Format | Example |
|-------|--------|---------|
| Development pre-release | `X.Y.Z.devN` | `1.9.0.dev28` |
| Release candidate | `X.Y.ZrcN` | `1.9.0rc1` |
| Final release | `X.Y.Z` | `1.9.0` |

The `N` in `.devN` is a monotonically increasing integer — never reset between dev cycles.

> **Important:** The version string in `manifest.json` must be PEP 440-valid. `devN` requires a digit (`dev28`), not a letter. Invalid versions cause HACS validation to fail.

---

## Pre-release Workflow

### 1. Bump the version

Edit `custom_components/casambi_bt/manifest.json`:

```json
"version": "1.9.0.dev28"
```

### 2. Commit the bump

```bash
git add custom_components/casambi_bt/manifest.json
git commit -m "chore: bump version to 1.9.0.dev28"
```

### 3. Push to main

```bash
git push origin main
```

### 4. Tag the release

```bash
git tag v1.9.0.dev28
git push origin v1.9.0.dev28
```

### 5. Create the GitHub pre-release

```bash
gh release create v1.9.0.dev28 \
  --prerelease \
  --title "v1.9.0.dev28" \
  --notes "$(cat <<'EOF'
## What's Changed

### New
- Short description of new feature

### Fixed
- Short description of bug fix

**Full Changelog**: https://github.com/Superkikim/casambi-bt-hass/compare/v1.9.0.dev27...v1.9.0.dev28
EOF
)"
```

---

## Final Release Workflow

A final release promotes an existing dev/rc to stable. No code changes are needed beyond the version bump.

### 1. Bump the version to stable

```json
"version": "1.9.0"
```

### 2. Commit, push, tag

```bash
git add custom_components/casambi_bt/manifest.json
git commit -m "chore: bump version to 1.9.0"
git push origin main
git tag v1.9.0
git push origin v1.9.0
```

### 3. Create the GitHub release (not a pre-release)

```bash
gh release create v1.9.0 \
  --title "v1.9.0" \
  --notes "$(cat <<'EOF'
## What's Changed

Summary of all changes since the previous stable release.

**Full Changelog**: https://github.com/Superkikim/casambi-bt-hass/compare/v1.8.2...v1.9.0
EOF
)"
```

> Do **not** use `--prerelease` for a final release. HACS picks up the latest non-prerelease tag as the stable version.

---

## Release Notes Format

Use this structure for the `--notes` body:

```markdown
## What's Changed

### New
- **Feature name**: one-line description

### Fixed
- Short description of bug fix (no issue number required)

### Breaking
- Only include this section if there are breaking changes

**Full Changelog**: https://github.com/Superkikim/casambi-bt-hass/compare/vPREV...vNEW
```

To get the list of commits since the last tag:

```bash
git log $(git describe --tags --abbrev=0)..HEAD --oneline
```

---

## HACS Considerations

- HACS tracks the **default branch** (`main`), not a specific branch URL.
- HACS exposes the **latest non-prerelease tag** as the stable version.
- Pre-release tags (`.devN`, `rcN`, `-betaN`) are hidden from regular users but visible under "Experimental".
- After pushing a tag, HACS picks it up automatically — no manual action needed.

---

## Quick Reference

```bash
# Check current version
cat custom_components/casambi_bt/manifest.json | grep version

# List recent tags
git tag --sort=-version:refname | head -10

# List recent GitHub releases
gh release list --limit 10

# Commits since last tag
git log $(git describe --tags --abbrev=0)..HEAD --oneline

# Delete a tag locally and remotely (if a mistake was made)
git tag -d vX.Y.Z
git push origin --delete vX.Y.Z
gh release delete vX.Y.Z --yes
```
