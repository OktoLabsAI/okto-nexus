# PR-04 — shared participant configuration contract

Date: 2026-11-05. Windows 11 10.0.26300, Python 3.13.1. Core 0.0.14,
Connector 0.0.12 and Nexus 0.3.3 remain on their authorized feature branches.
Scope: DX-01, with format/editor subscopes of DX-02/03. The participant `init`,
credential import/launch context, doctor negotiation and cooperation smoke are
not delivered by this foundation. The original plan and complete M1/M2 scope
are unchanged.

## Implementation

Core now has `participant_config`, distinct from `HarnessHTTPTemplate`. The
immutable, validated contract records client/build, format/revision, selected
file scope, entry, approved origin/endpoint and an environment reference.
Credential values, capabilities, executable commands and host paths are not
credential references. A dedicated participant variable namespace avoids
provider credential variables. The host retains authentication, credential
resolution, selected path, consent and persistence responsibilities.

Claude JSON and Codex TOML use their direct HTTP Bearer reference fields. Generic
JSON is explicitly marked as manual configuration; Pi is refused rather than
assigned an invented HTTP adapter. Existing managed `mcp-cap:` and native format
qualification remain enforced. No Server policy, runtime, grant or binding is
changed by the participant contract.

The two contracts reuse a shared structural Codex editor and existing JSON/TOML
hash/CAS/persistence helpers. Plans require an exact trusted predecessor for an
owned entry; unrelated JSON values, TOML bytes/comments and newline style are
preserved. Duplicate/invalid documents fail closed. Removal only touches the
still-owned entry, preserving later unrelated edits. Complex customized owned
TOML requires inspection instead of losing comments. Atomic persistence uses
the existing adjacent cooperative lock and backups; noncooperating final races
and Windows backup ACL verification remain the host's documented obligations.

## Validation

- `pr04-participant-contract-core-source.xml`: **100 passed**, including the
  new contract, existing editors/persistence, managed boundaries and public docs.
- `pr04-participant-contract-core-installed.xml`: **97 passed**, the runtime
  portion of that suite against the installed wheel outside the checkout.
- `pr04-participant-contract-connector-installed.xml`: **74 passed**, existing
  direct MCP config and approved managed-launch integration.
- `pr04-participant-contract-nexus-installed.xml`: **4 passed, 5 fixture errors**.
  The disposable tests lacked the SQL files that their fixture reads by path.
  Extracted the 158 SQL migrations from the installed candidate wheel into that
  fixture location; no production code or artifact changed.
- `pr04-participant-contract-nexus-followup.xml`: all **five affected cases
  passed**. The two Nexus reports are preserved, yielding nine passed cases.
- `pr04-participant-contract-import.json` and its audit script: installed Core
  import plus generic rendering made no socket/process/thread effect or
  non-code file read. Static import audit covered all **131 Core Python files**
  and rejected application/undeclared-dependency imports.
- Ruff E9/F, whitespace and `uv lock --check --find-links vendor/wheels` passed.

Fresh campaign directory:
`C:\Users\jpamb\AppData\Local\Temp\r3-participant-contract-sf2mkjgx`.
Core was built with `rtk proxy uv build --wheel` from a fresh source copy, then
all three artifacts were installed in a fresh validation venv. Copied tests ran
with `python -I -m pytest`, outside the repositories. The manifest verifies exact
Python source sets and bytes: Nexus **436**, Connector **117**, Core **131**;
Nexus's seven static assets also match. Core SHA-256:
`0468b54b72e418eaa6e0f3faee85c9fc1ec06c8081f90c4ece548f75f44962e7`.
That same wheel is vendored in both consumers; their version pins are unchanged.
Nexus/Connector runtime wheel payloads remain unchanged. No release was uploaded.
Core source commit/push: `7a58bd3`; Connector candidate commit/push: `7b2c3bf`.

## Real client format reading

`scripts/qualify_participant_formats.py` is reproducible with explicit executable
paths and a fresh `--directory`. It isolates home/config directories and removes
inherited provider credentials from the child environment. It generates entries
using the participant contract, applies them with backup/CAS, invokes only
`--version` and `mcp get`, and verifies the selected file remains unchanged.
A loopback listener counts any unexpected MCP requests.

`pr04-participant-contract-client-formats.json` records the **installed Core**
campaign: Claude Code **2.1.317** reads the project `.mcp.json` as HTTP and reports
**Pending approval**. Codex CLI **0.166.0** reads `config.toml` and reports the
expected streamable HTTP URL and `bearer_token_env_var`. Both preserved the file
and backup, and the listener saw **zero MCP HTTP requests**. Codex warned that
PATH helper aliases cannot be created under the temporary home; config reading
succeeded. No client was prompted, authenticated or given a model turn.

This proves parser acceptance for those builds on Windows. It does **not** prove
secret resolution in the eventual launcher/GUI, project trust approval, MCP
initialization, tool calling, participation or handoff completion. Missing
variables remain unproven; neither config parser is labeled ready. The equivalent
source campaign also passed and is recorded separately; it is overlapping proof.

Renderer references checked on 2026-11-05:
[official Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
and [official Claude Code MCP documentation](https://code.claude.com/docs/en/mcp).
The installed binaries, not the documentation alone, establish the parsing result.

## Remaining work

DX-01 is verified as the shared pure contract. DX-02/03 and PR-04 remain in
progress: connect/init must bind a retained review to identity, workspace,
protected credential and the selected file; recover partial local stages;
validate the actual client environment; and report independent proof levels.
Two-client authenticated cooperation, real productive M1, two-host execution,
native service/login qualification, attention and observation fronts remain
open under the fixed R3 plan. No personal configuration or credential was used.
