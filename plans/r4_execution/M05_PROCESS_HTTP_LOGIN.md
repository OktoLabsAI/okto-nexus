# Approved existing login and process-only MCP configuration

Date: September 30, 2026. Partial M05/M06/M09 increment; no gate closure.

When an approved provider home has no imported provider credential references, Nexus and Connector preserve that home and supply a typed Core-owned MCP configuration for the native process. Existing OAuth login files are neither copied nor edited. The protected session capability remains in the child environment; arguments contain only its environment-variable name and approved MCP URL.

Core 0.2.39.dev0 validates adapter, entry name, section, capability reference, bearer environment name and URL before launch. Codex receives a per-process TOML override with a unique session entry; its existing MCP entries remain subject to the approved provider home. Claude receives strict per-process MCP JSON. Imported-credential launches retain their existing isolated-home behavior. Wire requests cannot supply arbitrary additional arguments.

## Verification

The same Core wheel is installed in both consumers. Source, wheel and installed package bytes are compared before each suite. Core: 83 passed; Connector: 45 passed; Nexus: 15 passed; overlapping Nexus suite in an environment without the Connector application: 15 passed. Both environments pass pip check. Clean wheel import/resource and embedded/remote smoke checks passed.

The first source-package staging omitted public documentation and failed verification; corrected complete staging passed. Both logs are retained. Test-only native factories exercise composition and refusal paths, not real-provider acceptance. The existing real Pi evidence belongs to the prior published artifact set. Real Codex/Claude integrated acceptance remains pending. Preexisting Nexus UI assets are present in the wheel but excluded from this commit and UI acceptance.

Evidence: [coordinated manifest](test_runs_20260930_process_http.json), [installed runner](run_process_http_installed.py), and evidence/process-http-*.
