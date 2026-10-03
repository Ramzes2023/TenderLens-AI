# Contributing

Start with the [architecture](ARCHITECTURE.md), [security boundaries](SECURITY.md)
and [current scope](PROJECT.md). The repository is public, but currently has no
LICENSE file; discuss reuse/contribution terms with the author.

## Local workflow

1. Use a new branch from main and a Python 3.12 virtual environment.
2. Install `requirements-dev.txt`; copy `.env.example` only if you need a local demo.
3. Keep changes focused and add regression tests for changed behavior.
4. Run `python -m pytest -q`, `python -m compileall -q app tests scripts`
   and `git diff --check` in the virtual environment.
5. Open a PR explaining the concrete problem, result, tests and remaining limits.

Automated tests should use temporary data and mocked external services, not real
credentials, production databases or paid API calls. Never stage .env, tokens,
invitation URLs, database files, backups or model caches. Inspect screenshots too.

Documentation changes should preserve the distinction between local demo operation
and public deployment. Do not change release tags or deployment settings as part of
a documentation PR. For security-sensitive reports, do not post exploit credentials
or private data publicly; consult [SECURITY.md](SECURITY.md).
