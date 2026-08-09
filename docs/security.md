# Security Policy

SciEqLint analyzes untrusted document text. Security is part of the product contract.

## Supported versions

Security fixes are provided for the latest released minor version.

## Reporting a vulnerability

Do not open a public issue for a vulnerability. Use
[GitHub private vulnerability reporting](https://github.com/Kuhai9801/scieqlint/security/advisories/new)
or contact the maintainers listed in `MAINTAINERS.md`.

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
- call SymPy text parsers on document content,
- overwrite a consumed source, configuration, or baseline file through `check
  --output`, including exact and lexical path aliases plus hardlink and symlink
  aliases;
- overwrite a consumed source or configuration file through `graph --output`,
  including exact and lexical path aliases plus hardlink and symlink aliases.

Identity capture failures do not change stdout or already-loaded-document API
analysis, but any file-output operation refuses before creating or modifying its
destination when a consumed input's object identity is unavailable.

The lexical-role check follows the host path implementation. On a case-insensitive
POSIX filesystem, a case-only alias to a pathname whose object was replaced cannot be
inferred from POSIX spelling alone; the descriptor identity still protects aliases to
the object that was actually consumed. Ordinary `.` and `..` aliases are protected
when their traversed components are not symlinks; parent segments after a symlink
remain part of the raw caller role so distinct physical targets are not conflated.

## Dependency updates

Dependency updates should pass the normal CI loop. Security updates may be expedited, but they must not bypass tests that protect the runtime security contract.
