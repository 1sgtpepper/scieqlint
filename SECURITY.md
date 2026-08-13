# Security Policy

SciEqLint analyzes untrusted document text. Security is part of the product contract.

## Supported versions

Security fixes are provided for the latest released minor version in the current
major release line. Reports affecting older minors are assessed against the latest
release, and reporters may be asked to verify or upgrade before a fix is issued.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use
[GitHub private vulnerability reporting](https://github.com/1sgtpepper/scieqlint/security/advisories/new)
when available. If GitHub private reporting is unavailable, email
[sgtpepper1@proton.me](mailto:sgtpepper1@proton.me).

Please include:

- affected version or commit,
- operating system and Python version,
- minimal reproduction,
- expected behavior,
- observed behavior,
- whether arbitrary code execution, file read/write, denial of service, or data exposure is possible.

## Runtime security contract

The checker runtime must not:

- make network calls,
- execute notebooks,
- import user project modules,
- evaluate Python code from documents,
- run shell commands from the analysis core,
- write files except explicit `--output` or `init`,
- follow symlinks outside the project root by default,
- read ignored files unless explicitly passed,
- call SymPy text parsers on document content.

## Dependency updates

Dependency updates should pass the normal CI loop. Security updates may be expedited, but they must not bypass tests that protect the runtime security contract.
