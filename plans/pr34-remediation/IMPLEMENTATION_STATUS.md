# PR #34 remediation — execution status

Started 2026-09-22, Windows / PowerShell. **IN PROGRESS; final gate NOT PASSED.**

## Baseline

- Local and GitHub HEAD: `d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397`.
- GitHub base / local merge-base: `27b06fe48b9f95b35c94f50827fea83d178f4e12`.
- Baseline branch: `feature/harness-integrations`. User subsequently directed all development, milestone commits and pushes to `feature/v0.2.0`; created from the unchanged reference HEAD while preserving working changes. Package bumped to 0.2.0.
- Existing changes preserved: three generated dashboard files; `.nexus-policy-guardrail-test/`; six user-supplied specification files at repository root.
- Latest migration: 029. No user database opened or migrated.
- Instructions inspected: CLAUDE.md, CONTRIBUTING.md; no AGENTS.md discovered in repository or ancestor directories.
- Specification precedence: current remediation package supersedes historical frozen-port / no-thread / no-MessageService-change restrictions. CLAUDE.md's claims of no CI and main-only development are stale (repository has .github and this authorized PR branch).

## P00 — active

Baseline, defect register, contract map and 20 failing behavior regressions committed and pushed in 63c9623. See BASELINE.md for exact counts and evidence.

Commands/results:

- `git status --short --branch`, `git rev-parse HEAD`, `git merge-base HEAD origin/main`, `gh pr view 34 --json headRefOid,baseRefOid,headRefName,url`: reference unchanged.
- `.venv/Scripts/python.exe -m pytest --collect-only -q`: **FAIL**, 1830 collected, one Windows collection error (`os.geteuid` in test_claude_code_attach_connector.py); evidence `evidence/p00-collection.log`. This is baseline portability failure, not a remediation regression reproduction.
- `.venv/Scripts/python.exe -m pytest -q --ignore=tests/test_claude_code_attach_connector.py`: completed: 1814 passed, 13 failed, 4 skipped; evidence `evidence/p00-baseline.log`. Exclusion is explicit; excluded tests remain NOT_RUN.

## Pending gates

P01–P12 NOT_STARTED. No completion claims from historical PR counts. User explicitly approved the installed local Codex and subsequently Claude for real tests. Versions observed: codex-cli 0.155.1; Claude Code 2.1.277. Keep native tests in temporary project directories, preserve security controls, never pass the Nexus operator key. Attach requires a dedicated test session; never select a personal session. Pi native tests remain NOT_RUN by user decision.

Next: P02 versioned contracts and registry, then approved endpoint/profile persistence. Remaining seven red regressions belong to later phases. No legacy producer may be switched to a private, unintegrated dispatcher. Update this file and `05_BACKLOG.json` per unit.
