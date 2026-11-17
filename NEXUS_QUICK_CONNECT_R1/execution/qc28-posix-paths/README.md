# QC28 POSIX installed-path qualification

**202 passed, 0 failed, 0 skipped**, using Python 3.13.1 in an owned Ubuntu 22.04 WSL2 `/tmp` environment. This is selected installed-package qualification, not a native Ubuntu or full Linux CI matrix.

The five unchanged copied modules cover parser grammar (41), Git adapter (43), Git trust (3), project resolution (47) and public-ID choices (65). Three new tests use the real Linux filesystem: `Repo` and `repo` have distinct inodes/profiles; a symlink resolves the same physical identity/profile; literal backslashes do not become POSIX directory separators. The actual paths/device/inodes are retained in `qualification.json`.

All three package families import from the owned Linux venv. All 1,027 package payload files match the exact Windows-qualified wheels, and 1,780 source pins remain unchanged. No product source was copied onto the Python import path. The project/ID semantic tests retain their declared fake-GET scope; this run does not prove Linux SQLite/HTTP authority, service lifecycle or provider behavior.

The uv 0.10.7 binary was downloaded from the [official release](https://github.com/astral-sh/uv/releases/tag/0.10.7) and checked against its [official archive SHA256](https://github.com/astral-sh/uv/releases/download/0.10.7/uv-x86_64-unknown-linux-gnu.tar.gz.sha256). The complete verified archive SHA256 is recorded as `actual_sha256` in `evidence/uv-download.json`. Only the `uv` archive member was extracted. Runtime, venv, dependencies, HOME/XDG/cache/tmp all remained under the allocated `/tmp/nexus-qc28-*` root. No apt/sudo, global/user install, dotfile, WSL configuration, Windows session or personal prefix was changed. No service or provider was invoked.

Two setup antecedents are preserved: a first `/tmp` directory disappeared between short WSL calls before downloads; a finite owned observer kept the next window alive. The first uv-version assertion expected an optional build suffix and failed before Python installation; the continuation checked the exact `uv 0.10.7` version and verified binary hash. No failing product test was changed or rerun.

Evidence was copied to this Windows directory before normal stop-file shutdown of the keeper. Its Linux PID was observed absent; no signal or `wsl --shutdown/--terminate` was used. The original keeper exit code was not reaped by the cleanup process. Each pytest process group was already empty. Runtime files are temporary and may disappear when the guest becomes idle; curated evidence remains here.
