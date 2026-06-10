# Security Policy

SciEqLint analyzes untrusted document text. Security is part of the product contract.

## Supported versions

Security fixes are provided for the latest released minor version. Maintainers
may also provide fixes for earlier supported release lines when a vulnerability
affects active downstream users.

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
- follow symlinks outside the project root during project discovery,
- read ignored files unless explicitly passed,
- call SymPy text parsers on document content.

Explicitly passed files are treated as caller-selected inputs, including when
the explicit path is a symlink. Project discovery still skips files whose
resolved path is outside `project.root`.

## Dependency updates

Dependency updates should pass the normal CI loop. Security updates may be expedited, but they must not bypass tests that protect the runtime security contract.
