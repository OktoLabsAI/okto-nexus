"""Record remote renewal qualification without changing the fixed R3 inventory."""
import hashlib
import json
from pathlib import Path
import sys

BASE = Path(__file__).parent
ROOT = Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
CONNECTOR = ROOT.parent / 'okto-nexus-connector'
REL = 'plans/agent_ops/evidence/pr03-remote-renewal'
DIR = ROOT / REL
reports = json.loads((DIR / 'reports.json').read_text())
proof = json.loads((DIR / 'candidate-v2/package-proof.json').read_text())
counts = {name: result['tests'] for name, result in reports['installed'].items()}
nexus = proof['packages']['okto_nexus']
connector = proof['packages']['okto_nexus_connector']
assert counts == {'nexus': 66, 'connector': 233}, counts
summary = (f"Remote grant renewal is qualified with real loopback HTTP/WebSocket, authenticated TCP IPC and DaemonApp: "
    "expiry/exhaustion, lost issuance response, same-receipt recovery, unchanged prior leases/sessions, explicit close/new work, "
    "canonical key rotation and protected replacement, stale key/ticket/review refusal and historical recovery after revocation. "
    "Completed Connector reuse authenticates the current identity and exact approved binding without mutating the old bootstrap "
    "or replaying Finish/probe; pending setup remains anchored to its original credential epoch. Submitted issuance stays "
    "uncertain during login/vault/recovery failure; a transport failure reading an already confirmed receipt does not reopen issuance uncertainty. "
    f"Installed tests: Nexus {counts['nexus']}, Connector {counts['connector']}. Native/provider behavior remains synthetic; "
    "real provider/TLS/two-host, OS-vault lifecycle, native services and complete M1/M2/R3 remain open.")
doc = f'''# PR-03 — remote grant renewal and credential replacement

Status: implemented and verified for the Windows loopback contract below. Full PR-03 and R3 remain IN_PROGRESS.

{summary}

## Delivered behavior

- Reuse after explicit key replacement is limited to a completed configuration, one APPLIED intent and the exact current APPROVED binding. Current Server/agent/origin, local installation/configuration, consent, child map, proposal and Finish result must still agree. No pending local review or unfinished startup operation may enter this path.
- The Connector checks authenticated current identity and binding, then rechecks retained host facts before daemon effects. A concurrent identity/profile/root/intent/binding or physical selection change refuses reuse. The old bootstrap epoch is historical; it is never rewritten or accepted to finish a pending setup with another key.
- The existing key rotation endpoint and `identity replace-credential` remain explicit. Rotation is one-shot and has no automatic retry guarantee. Reconnect does not issue grants, repeat probes or submit work. Current revocation and policy remain authoritative.
- Existing human `work authorize` review/issue/recover APIs remain unchanged. A submitted issuance stays `unconfirmed` on login, vault or recovery failure. A confirmed receipt's read-only recovery cannot make the issuance uncertain again merely because the transport labels POST failures as possibly effective. No new API, migration, authority or Core protocol was introduced.

## Qualification

| Package | Version | Installed tests | Exact package files | Wheel SHA-256 |
|---|---|---:|---:|---|
| Nexus | 0.3.3 | {counts['nexus']} | {nexus['file_count']} | `{nexus['wheel_sha256']}` |
| Connector | 0.0.12 | {counts['connector']} | {connector['file_count']} | `{connector['wheel_sha256']}` |
| Core | 0.0.14 | exercised by both suites | unchanged vendored wheel | `{proof['core_sha256']}` |

Both declared installed suites pass without failure/error/skip, outside the checkouts with noneditable-wheel and module-origin guards. Nexus candidate-v2 reuses the exact Connector wheel qualified in candidate-v1. Candidate-v2 adds only the final correction to confirmed receipt recovery in Nexus; the final Nexus suite includes the joint four-case campaign and all 19 uncertainty cases. Source/build/wheel/install file hashes match the final product. There is no registry publication or merge.

The four joint cases use the actual Server, Connector DaemonApp, real authenticated loopback TCP IPC, control/heartbeat, inventory barrier, WebSocket dispatch, Core storage, human OperatorProfile and canonical APIs. They cover:

1. Naturally exhausted grant and an explicitly expired grant fixture. Loss is injected after actual issuance commit; reopening the work checkpoint recovers one grant/receipt without another issue. Existing sessions, leases and operations remain unchanged until an explicit close. Separately requested new work uses the new grant.
2. Explicit canonical rotation and protected Connector replacement. Old key and derived ticket are refused; a stale grant review conflicts. Completed reconnect preserves binding, bootstrap, proposals and Finish records without another probe. Fresh inventory/authority admit separately requested work with the current epoch.
3. Revocation before review and after uncertain issuance. Recovery returns historical metadata without reactivating the grant; participant key requests to review/issue/recover are refused.

Expiry is created by changing only the isolated grant expiry after a real first operation; clocks, tickets, leases, capacity and admission are not extended or bypassed. Native process/provider responses and discovery/probe effects are explicit doubles. The daemon runs foreground inside the test, and the spawn request reuses that owner; no Windows service is installed. Operator storage is an isolated memory vault and host storage an explicitly approved restricted temporary file vault.

Source qualification has 19 new operator cases, 37 existing authorization/operator cases, 6 existing CLI cases and 4 joint cases. Connector has 233 unique qualified cases, including 28 new cases. Source reports overlap with installed runs and are not added to installed totals. Initial failures remain recorded: the intended epoch mismatch; a CAS error-code expectation; uncertainty classification; and integration fixture assumptions about IPC selection, readiness, inventory, operation stage and grant accounting. `source/integrated/campaign-summary.json` gives exact attempts and limits. Public copies redact synthetic credential literals; raw reports remain outside the repository, with original/public hashes and redaction counts in `reports.json`.

Full Ruff checks pass for the changed product/new test files, and tracked/untracked whitespace checks pass. No already-closed bootstrap evidence was changed. This milestone does not qualify OS-vault access, real native/provider context, service login/logout/crash/reboot, two physical hosts or productive M1/M2. Those limits do not change the fixed plan or its acceptance criteria.

Usage: [terminal work](../../../docs/terminal-work.md), [remote setup and completed reuse](../../../docs/remote-project-setup.md). Evidence: [reports](pr03-remote-renewal/reports.json), [artifact manifest](pr03-remote-renewal/artifact-manifest.json).
'''
(ROOT / 'plans/agent_ops/evidence/pr03-remote-renewal.md').write_text(doc, encoding='utf-8')
(CONNECTOR / 'docs/evidence/remote-rotation/README.md').write_text(f'''# Completed remote setup after credential replacement

Connector 0.0.12 passed {counts['connector']} installed tests, including 28 new source cases. The exact {connector['file_count']} source/build/wheel/install files are pinned by `{connector['wheel_sha256']}`; Core 0.0.14 is unchanged. Nexus integration candidate: `{nexus['wheel_sha256']}`.

Current authenticated identity and exact approved binding permit only completed setup reuse after explicit key replacement. Bootstrap/Finish history remains unchanged; pending setup, local review, missing or drifting bindings, unfinished startup and concurrent host changes remain refused. Reconnect does not apply a proposal, probe, issue a grant or submit work. Existing daemon reuse/reload remains the lifecycle path.

The source regression had 232 passes and one error-code expectation mismatch for a profile change; four overlapping CAS retests passed after correcting that expectation. The final installed suite reruns all 233 identities with zero failure/error/skip. Initial epoch failures are preserved. Full Ruff on the changed product/new test files and whitespace checks pass.

The Nexus campaign adds four installed cases with real HTTP/WebSocket/TCP IPC and DaemonApp, synthetic native/provider behavior and isolated vaults. It qualifies renewal, loss recovery, explicit rotation, stale credential/ticket refusal and historical revocation recovery; it does not qualify real TLS/two-host deployment, OS vaults, native services or provider work. No previous evidence was rewritten.

[Usage](../../connection-configuration.md), [reports](reports.json), [package proof](package-proof.json), [raw-byte manifest](artifact-manifest.json).
''', encoding='utf-8')
if '--docs-only' in sys.argv:
    raise SystemExit(0)
connector_commit = sys.argv[1]
assert len(connector_commit) == 40 and all(c in '0123456789abcdef' for c in connector_commit)
ledger_path = ROOT / 'plans/agent_ops/ledger.json'
ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
assert hashlib.sha256((ROOT / ledger['plan']).read_text(encoding='utf-8').encode()).hexdigest() == ledger['plan_sha256']
sets = {key: set(ledger[key]) for key in ('tasks', 'scenarios', 'invariants', 'completion_criteria')}
evidence = [REL + '/reports.json', REL + '/artifact-manifest.json', REL + '/candidate-v2/package-proof.json',
    REL + '/candidate-v2/nexus/installed.xml', REL + '/candidate-v2/nexus/qualification.json',
    REL + '/candidate-v1/connector/installed.xml', REL + '/candidate-v1/connector/qualification.json',
    'plans/agent_ops/evidence/pr03-remote-renewal.md']
changes = json.loads((BASE / 'changed-paths.json').read_text())
files = [prefix + path for repo, prefix in ((ROOT, ''), (CONNECTOR, '../okto-nexus-connector/'))
    for path in changes[str(repo)] if path.startswith(('src/', 'tests/', 'docs/'))]
scope = dict(remote_grant_renewal_http_ipc_wss='VERIFIED', remote_rotation_completed_reuse='VERIFIED',
    remote_pending_grant_uncertainty='VERIFIED', remote_confirmed_receipt_read_failure='VERIFIED')
for key in ('DX-09', 'DX-15', 'DX-17', 'DX-18', 'DX-19', 'DX-20', 'DX-21'):
    item = ledger['tasks'][key]
    item.setdefault('subscopes', {}).update(scope)
    item['files'] = sorted(set(item.get('files', []) + files))
    item['tests'] = sorted(set(item.get('tests', []) + evidence))
    item['result'] = item.get('result', '') + '\n2026-11-07 remote renewal update: ' + summary
    item.setdefault('limitations', []).append('The remote renewal contract is now verified with Windows loopback HTTP/WSS/TCP IPC and synthetic native/provider peers. Real provider, two-host/TLS, OS-vault/service lifecycle and complete M1/M2 remain open.')
for key in ('DX-T02', 'DX-T40', 'DX-T41', 'DX-T48'):
    item = ledger['scenarios'][key]
    item.setdefault('subscopes', {}).update(scope)
    item['evidence'] = sorted(set(item.get('evidence', []) + evidence))
    item['result'] = item.get('result', '') + '\n2026-11-07 remote renewal update: ' + summary
for key in ('AC-05', 'AC-07', 'AC-08', 'AC-14', 'AC-17'):
    item = ledger['completion_criteria'][key]
    item.setdefault('subscopes', {})['remote_renewal_installed_contract'] = 'VERIFIED'
    item['evidence'] = sorted(set(item.get('evidence', []) + evidence))
ledger['milestones']['PR-03']['evidence'] = sorted(set(ledger['milestones']['PR-03']['evidence'] + evidence))
ledger['campaigns']['pr03_remote_renewal_windows_loopback'] = dict(status='VERIFIED',
    scope='Windows loopback HTTP/WSS, actual DaemonApp and TCP IPC; synthetic native/provider and isolated vaults',
    evidence=evidence, nexus_installed=counts['nexus'], connector_installed=counts['connector'],
    connector_commit=connector_commit, core_changed=False)
ledger['history'].append(dict(date='2026-11-07', milestone='PR-03', status='IN_PROGRESS',
    summary=summary, evidence=evidence, connector_commit=connector_commit))
ledger['updated_at'] = '2026-11-07'
assert all(set(ledger[key]) == value for key, value in sets.items())
ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
with (ROOT / 'LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md').open('a', encoding='utf-8') as stream:
    stream.write(f'''\n\n## 2026-11-07 — PR-03: renovação remota e reconexão após troca de chave

Quatro cenários conjuntos qualificaram renovação por esgotamento/expiração, resposta perdida, rotação explícita, reconexão concluída e revogação com HTTP/WebSocket, IPC TCP e DaemonApp reais. O harness/provedor é sintético. Bootstrap e Finish históricos permanecem imutáveis; setup pendente mantém o epoch original. Emissão pendente conserva incerteza durante falha de acesso, enquanto falha de leitura de recibo confirmado não reabre a emissão.

Pacotes instalados: **Nexus {counts['nexus']}/{counts['nexus']} e Connector {counts['connector']}/{counts['connector']}**, sem somar retestes. Core inalterado. Connector commit/push `{connector_commit}`. Plano e inventário fixos preservados; M1/M2 produtivos, serviços/cofres nativos, TLS/dois hosts e R3 integral permanecem abertos. [Evidências e limites](plans/agent_ops/evidence/pr03-remote-renewal.md).
''')
with (ROOT / 'plans/agent_ops/implementation-report.md').open('a', encoding='utf-8') as stream:
    stream.write('\n\n## PR-03 — remote renewal and explicit credential replacement\n\n' + summary +
        '\n\n[Qualification, attempts, package pins and limits](evidence/pr03-remote-renewal.md).\n')
print(json.dumps(dict(counts=counts, connector_commit=connector_commit, fixed_inventory_preserved=True, r3_complete=False)))
