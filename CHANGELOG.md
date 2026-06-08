# Changelog

All notable changes to SciEqLint should be documented here.

Release notes must use these sections:

- Added
- Changed
- Fixed
- Deprecated
- Removed
- Migration notes
- Known limitations

## Unreleased

### Added

- Complete v11.1 specification and OSS contributor scaffold.
- v0.1.0 Markdown/MyST analyzer for simple scalar algebra and equation references.
- v0.1.1 GitHub annotation output and pre-commit metadata.
- v0.1.2 dimension config surface and configured dimension diagnostics for supported
  equality, addition, subtraction, multiplication, division, and integer-power expressions.
- CI, docs, issue templates, labels, schemas, examples, and release checklists.

### Changed

- Nothing yet.

### Fixed

- Nothing yet.

### Deprecated

- Nothing yet.

### Removed

- Nothing yet.

### Migration notes

- No released package exists yet.

### Known limitations

- The analyzer is intentionally small: Markdown/MyST only, simple scalar polynomial algebra,
  supported equation references, and configured dimension checks only.
- v0.1.2 dimensions require explicit `[vars]` config. Presets, aliases, unit databases,
  and dimension CLI override flags are deferred.
