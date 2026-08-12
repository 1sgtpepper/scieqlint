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
- call SymPy text parsers on document content,
- overwrite a consumed source, configuration, or baseline file through `check
  --output`, including exact and lexical path aliases plus hardlink and symlink
  aliases;
- overwrite a consumed source or configuration file through `graph --output`,
  including exact and lexical path aliases plus hardlink and symlink aliases.

Identity or path-role metadata failures do not change stdout or already-loaded-document
API analysis, but any file-output operation refuses before creating or modifying its
destination when a consumed input's safety identity is incomplete.
The output guard compares an existing destination with both the object consumed
earlier and the object currently reached through every consumed source, configuration,
or baseline role. Existing destinations are opened without creation; a destination
that disappears during the open protocol is retried exclusively and is never created
through a dangling symlink.

Where the host supports directory-descriptor opens, the physical output parent is
pinned before exclusive creation, so retargeting that parent cannot redirect creation
into a deleted consumed role. Hosts without that primitive retain the role and object
checks, but hostile parent-directory retargeting between validation and creation is
outside the guarantee.

The lexical-role check follows the host path implementation. On a case-insensitive
POSIX filesystem, a case-only alias to a pathname whose object was replaced cannot be
inferred from POSIX spelling alone; the descriptor identity still protects aliases to
the object that was actually consumed. Ordinary `.` and `..` aliases are protected
when their traversed components are not symlinks; parent segments after a symlink
remain part of the raw caller role so distinct physical targets are not conflated.

## Dependency updates

Dependency updates should pass the normal CI loop. Security updates may be expedited, but they must not bypass tests that protect the runtime security contract.
