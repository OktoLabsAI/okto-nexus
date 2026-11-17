# QC-010: local Git naming adapter

The isolated adapter and 43 focused tests passed on Windows/CPython 3.13. This is not a CLI, installed-package, cross-platform or paid-harness qualification. Source/test/XML pins and exact commands are in `qualification.json`; no ledger was promoted.

The frozen DTO contains only `name`, `source`, `status`, `reason`. Origins remain internal bytes/text and never become execution identity or a workspace/root selector. `plan=True` performs no executable discovery and launches no process. The caller must bypass discovery when recovering an approved/saved selection. Shared `NameDiscovery` enums are used without adding new reason strings.

Git is invoked directly with argv and `shell=False`; RTK prefixes apply to this agent's shell commands. The host's absolute PATH installation entries are filtered to exclude the project/current directory, relative entries, project-target symlinks and UNC executable paths. No installation, version probe, auth read or remote operation occurs. System/global config and inherited `GIT_*` overrides are disabled. Config naming reads are explicitly local/worktree and `--no-includes`; no global remote, upstream or URL rewriting is a name source.

At most six calls share one two-second deadline and each retains at most 64 KiB of stdout+stderr together (384 KiB total). Nonblocking readers do not accumulate oversized output or wait indefinitely for a descendant-held pipe. PATH enumeration is capped at64 entries and checks the same deadline. Timeout/overflow kills and waits for the owned process. OS-level spawn/filesystem stalls are not a hard real-time guarantee; this limitation is explicit rather than hidden by the subprocess timeout.

Real temporary Git repositories cover origin formats, ambiguous values, nested repositories, a linked `.git` file, enabled worktree config, config/environment injection, UTF-8 labels and privacy. Controlled reader/process cases cover ownership rejection, deadline and output failure paths. Integration scenarios for exact selectors, saved-name recovery, workspace identity, CLI help and persisted/telemetry redaction remain pending. All children were awaited, and no service or browser was created.

Primary documentation: [git-config](https://git-scm.com/docs/git-config), [git environment](https://git-scm.com/docs/git), [git-worktree](https://git-scm.com/docs/git-worktree). These establish config scopes, includes, worktree configuration and environment controls; the budget/privacy restrictions are Nexus requirements.
