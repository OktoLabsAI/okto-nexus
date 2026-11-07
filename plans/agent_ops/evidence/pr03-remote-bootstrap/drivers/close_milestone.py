"""Record only the qualified remote-setup scope; preserve fixed R3 inventory."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
CONNECTOR = ROOT.parent / 'okto-nexus-connector'
REL = 'plans/agent_ops/evidence/pr03-remote-bootstrap'
DIR = ROOT / REL
reports = json.loads((DIR / 'reports.json').read_text())
proof = json.loads((DIR / 'candidate-v1/package-proof.json').read_text())
nexus = proof['packages']['okto_nexus']
connector = proof['packages']['okto_nexus_connector']
counts = {name: value['tests'] for name, value in reports['installed'].items()}
connector_commit = sys.argv[1] if len(sys.argv) > 1 else None
assert all(not reports['installed'][name][kind] for name in counts for kind in ('failures', 'errors', 'skips'))
summary = (f"Remote identity/workspace bootstrap and the single reviewed project setup are now qualified in Windows loopback "
    f"with Nexus {counts['nexus']} and Connector {counts['connector']} installed tests. The six joint cases use real TCP/WSS, "
    "a real human operator session, canonical decisions/Finish, durable host state and explicit synthetic native/provider/vault fixtures. "
    "Bootstrap is a partial commit with one-shot key delivery, no grant/endpoint or runtime/location activation. "
    "Current root/review/credential guards fence prepare, decision and apply. Local amendments retain original bootstrap/history, "
    "promote only a matching authenticated handoff and recover a racing prior Finish. Full real-provider/two-host M1/M2, "
    "native services, real credential/grant renewal and joint R3 acceptance remain open.")
evidence = [REL + '/reports.json', REL + '/candidate-v1/package-proof.json',
    REL + '/candidate-v1/nexus/installed.xml', REL + '/candidate-v1/nexus/qualification.json',
    REL + '/candidate-v1/nexus-schema-focal/installed.xml', REL + '/candidate-v1/nexus-schema-focal/qualification.json',
    REL + '/candidate-v1/connector/installed.xml', REL + '/candidate-v1/connector/qualification.json',
    REL + '/artifact-manifest.json', 'plans/agent_ops/evidence/pr03-remote-bootstrap.md']
doc = f'''# PR-03 — remote identity and reviewed project setup

Status: implemented and verified for the Windows/loopback contract below. PR-03 and full R3 remain IN_PROGRESS.

{summary}

## Delivered behavior

- Connector exports a bounded, path-free draft before vault access, registration, probes or daemon startup. Private physical selections remain on that host.
- The human operator reviews identity, permissions, workspace, installation, portable configuration, grant limits, native-decision policy and any previous-machine revocation. Existing identities retain their current permissions and key.
- Partial bootstrap atomically creates only the authorized identity/workspace and key hash plus receipt. The plaintext key is returned once and the CLI delivers it only with three terminal streams; JSON, checkpoints and the public handoff never contain it. Lost plaintext is unavailable, never reissued or rotated by retry.
- Authenticated subject recovery returns public metadata for the exact root; knowledge of the root is insufficient authority. Capability version, Server origin/ID, subject, current credential epoch, child map and draft revision are checked before credential import or continuation.
- Prepare/realize/apply remain the existing R4 protocol. Only the exact reviewed root may prepare before remote execution policy is enabled; execution admission remains unchanged. Human comparison uses canonical metadata and the existing approval API. Finish commits configuration, policy and grant together.
- Explicit local re-review preserves the active draft and immutable bootstrap while storing one pending amendment. New material choices receive a durable consent ID; Server issues new affected child IDs. Old requests keep their receipts and stop background continuation. CAS prevents delayed responses from overwriting a promoted selection.
- If a prior Finish commits while an amendment is pending, authenticated recovery preserves that Finish and archives the unapplied amendment. A completed setup cannot be amended or recreate removed resources. Current revocation and changed credentials remain fences.
- Server migration 167 is additive. Connector schema 17 preserves earlier records. The pure origin helper is shared inside Nexus without importing an outbound adapter into the application contract. Core has no change in this milestone.

## Qualification

| Installed package | Version | Tests | Files matched source/build/wheel/install | Wheel SHA-256 |
|---|---|---:|---:|---|
| Nexus | 0.3.3 | {counts['nexus']} | {nexus['file_count']} | `{nexus['wheel_sha256']}` |
| Connector | 0.0.12 | {counts['connector']} | {connector['file_count']} | `{connector['wheel_sha256']}` |
| Core | 0.0.14 | compatibility exercised by both suites | unchanged vendored wheel | `{proof['core_sha256']}` |

All declared installed test identities have a latest passing result, with no unresolved failure/error/skip, outside the checkouts. The Nexus first attempt had 186 passing cases and one failure because the test runner had not copied `plans/contratos/http-target.schema.json`; the same case passes after copying that supporting schema, against the unchanged wheel. The two closed XMLs remain separate: 188 observations, 187 unique identities. Connector passed all 276 cases in one run. Import guards verify every loaded Nexus, Connector and Core module comes from the candidate's site-packages; metadata verifies noneditable wheel installation. Exact commands, copied test hashes, module paths, dependency versions and XMLs are retained in the qualification reports. Source reports overlap and are not added to installed counts.

Ruff reports no diagnostics in the 28 changed Nexus Python files and no introduced diagnostics in the 25 changed Connector Python files. Connector retains 69 pre-existing diagnostics in those files (the baseline had 71); these are not described as a clean repository-wide lint run. After installed qualification, the new Connector test file was formatted to remove 12 E701 diagnostics; its syntax tree was checked unchanged and product bytes were unchanged. `static/` retains the comparison and exact pre/post test hashes. Git diff whitespace checks pass.

The six joint cases cover normal setup, lost operator decision response, lost apply response, Server-side review drift, changed local project with a new realization, and a Finish arriving while a local amendment is pending. The final case models the delayed approved request through real HTTP without persisting its acknowledgement; it is not an OS-crash campaign. Every completed case retains one canonical identity/binding/grant/Finish, one installation probe and no productive task. Real control negotiation and heartbeat establish inventory readiness; no SQL readiness shortcut is used.

Source regressions include 77 Server cases and 57 operator cases; later directed operator checks grow to 25 and the six joint identities are qualified across the initial/retest XMLs. Connector's final source union is 276 identities: 275 in regression and 55 in the focal report, with 54 overlaps. The final installed suites rerun their declared complete nodes against the final candidate. See `reports.json` for exact per-report totals.

Initial failures remain retained: Server audit/fixture/wiring corrections; Connector fixture/schema expectations and recovered orphan-vault handling; the root fixture's material callback, real control/producer identity, and exact stale-handoff error expectation. The Connector broad regression's one failure was an older SimpleNamespace fixture missing the optional remote_setup field; the focal and installed runs include its correction. Read review also closed ignored operator startup flags, lost-authentication uncertainty, one-shot material messaging, previous-machine effects and exact seven-field Finish recovery. No initial XML was replaced.

## Retention, recovery and limits

Server allows 1,024 retained roots per operator and 32 reviews per root, each review at most 64 KiB. Capacity refusal precedes pointer changes; identical replay and recovery remain available. There is no automatic pruning or expiry. `keep_agents=True` reset preserves roots/reviews with identities and configuration; full reset removes them. Connector allows 32 retained roots, one pending local review, 16 history entries, 64 KiB per record and a 4 MiB state file, reserving room for a racing Finish receipt. Full capacity refuses new allocation instead of deleting recovery data.

Bootstrap, vault and host effects are not a distributed transaction. No infinite idempotency or exactly-once external execution is claimed. The default protocol continues to treat host paths/digests as authenticated host claims, not independent OS proof. A changed concrete startup plan with startup still enabled uses existing service controls; a pending setup does not silently substitute it.

Qualification uses a single Windows machine, loopback HTTP/WSS, synthetic executable bytes and probe/provider doubles, an isolated memory vault for operator sessions and a temporary restricted file vault for the agent. It does not qualify real TLS/two-host deployment, OS vault availability, login/logout/reboot/crash, provider work or MCP-client cooperation. No native service, personal provider credential, package registry publication or merge was performed.

Rollback preserves canonical data: migration 167 is not destructively reversed, and reverting a binary does not revoke already committed grants or remove identities. Use the existing authorized configuration/revocation controls when those effects need to change. Keep the database and Connector state/vault for recovery. Do not delete state or choose a new root to retry an uncertain request.

Usage: [remote project setup](../../../docs/remote-project-setup.md). Raw evidence: [artifact manifest](pr03-remote-bootstrap/artifact-manifest.json), [reports](pr03-remote-bootstrap/reports.json).
'''
(ROOT / 'plans/agent_ops/evidence/pr03-remote-bootstrap.md').write_text(doc, encoding='utf-8')
connector_doc = f'''# Remote project setup qualification

Connector 0.0.12 is qualified with Nexus 0.3.3 and unchanged Core 0.0.14.
The installed wheel passed {counts['connector']} tests with no failure/error/skip; {connector['file_count']} package files match source, detached build, wheel and installation byte for byte.

Wheel: `{connector['wheel_sha256']}`. Nexus integration wheel: `{nexus['wheel_sha256']}`. Core: `{proof['core_sha256']}`.

Host drafts, current authenticated handoffs, exact identity import, durable child maps, explicit local re-review, delayed-response CAS and racing-Finish recovery reuse the existing R4 services. No administrative credential enters the host. Retention and concrete-startup-plan limits are described in [connection configuration](../../connection-configuration.md).

Source qualification has 276 unique latest passing identities across the final regression/focal reports; reports overlap. The single broad-regression failure came from an older background fixture without the optional remote_setup field and is retained alongside its correction. Installed tests rerun the complete declared node list against the final wheel outside the checkout with import guards for all three packages.

The new test file received formatting-only changes after this installed run; its Python syntax tree was verified unchanged. Product source and wheel bytes did not change. Lint comparison finds no newly introduced diagnostics; 69 existing diagnostics remain in the changed files.

The Nexus campaign also covers six joint real TCP/WSS cases: ordinary setup, lost decision/apply responses, Server/local re-review and a prior Finish arriving during local amendment. Native/provider behavior and vault facilities are explicitly simulated or isolated. This is not a two-host deployment, real-provider, native-service or M1/M2 acceptance claim. No package was published to a registry.

[Reports](reports.json), [package proof](package-proof.json), [raw artifact manifest](artifact-manifest.json).
'''
(CONNECTOR / 'docs/evidence/remote-bootstrap/README.md').write_text(connector_doc, encoding='utf-8')
if '--docs-only' in sys.argv:
    raise SystemExit(0)
ledger_path = ROOT / 'plans/agent_ops/ledger.json'
ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
assert hashlib.sha256((ROOT / ledger['plan']).read_text(encoding='utf-8').encode()).hexdigest() == ledger['plan_sha256']
original_sets = {k: set(ledger[k]) for k in ('tasks', 'scenarios', 'invariants', 'completion_criteria')}
scope = dict(remote_identity_workspace_bootstrap='VERIFIED', remote_operator_single_review_and_finish='VERIFIED',
    remote_one_shot_key_and_current_epoch='VERIFIED', remote_same_root_local_amendment_and_finish_race='VERIFIED',
    remote_noneditable_joint_packages='VERIFIED')
paths = []
precommit_paths = json.loads((Path(__file__).parent / 'changed-paths.json').read_text())
for repo, prefix in ((ROOT, ''), (CONNECTOR, '../okto-nexus-connector/')):
    changed = precommit_paths[str(repo)]
    paths += [prefix + p for p in changed if p.startswith(('src/', 'tests/', 'docs/')) and '/evidence/' not in p]
limitation = ('Remote bootstrap is now installed-qualified in Windows loopback with synthetic native/provider/vault fixtures. '
    'Real TLS/two-host, OS-vault/service lifecycle, provider work, credential/grant renewal and productive M1/M2 remain unqualified by this milestone.')
for key in ('DX-15', 'DX-16', 'DX-17', 'DX-18', 'DX-19', 'DX-21'):
    item = ledger['tasks'][key]
    item.setdefault('subscopes', {}).update(scope)
    item['files'] = sorted(set(item.get('files', []) + paths + ['docs/remote-project-setup.md']))
    item['tests'] = sorted(set(item.get('tests', []) + evidence))
    item['result'] = item.get('result', '') + '\n2026-11-07 remote-bootstrap update (supersedes prior bootstrap limitation): ' + summary
    item['limitations'] = [value for value in item.get('limitations', []) if not any(term in value.lower()
        for term in ('bootstrap', 'unified new identity/setup', 'remote identity provisioning'))] + [limitation]
for key in ('DX-T38', 'DX-T40', 'DX-T41', 'DX-T42', 'DX-T45', 'DX-T46', 'DX-T51'):
    item = ledger['scenarios'][key]
    item.setdefault('subscopes', {}).update(scope)
    item['evidence'] = sorted(set(item.get('evidence', []) + evidence))
    item['result'] = item.get('result', '') + '\n2026-11-07 remote-bootstrap update (supersedes prior bootstrap limitation): ' + summary
for key in ('AC-05', 'AC-07', 'AC-08'):
    item = ledger['completion_criteria'][key]
    item.setdefault('subscopes', {})['remote_setup_installed_contract'] = 'VERIFIED'
    item['evidence'] = sorted(set(item.get('evidence', []) + evidence))
ledger['milestones']['PR-03']['evidence'] = sorted(set(ledger['milestones']['PR-03']['evidence'] + evidence))
ledger['campaigns']['pr03_remote_bootstrap_windows_loopback'] = dict(status='VERIFIED',
    scope='Single Windows host, real loopback TCP/WSS, synthetic native/provider fixtures; no native service or productive M1/M2',
    evidence=evidence, nexus_installed=counts['nexus'], connector_installed=counts['connector'],
    connector_commit=connector_commit, core_changed=False)
ledger['history'].append(dict(date='2026-11-07', milestone='PR-03', status='IN_PROGRESS', summary=summary,
    evidence=evidence, connector_commit=connector_commit))
ledger['updated_at'] = '2026-11-07'
assert all(set(ledger[k]) == ids for k, ids in original_sets.items())
ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
markdown = f'''\n\n## 2026-11-07 — PR-03: bootstrap remoto e revisão no mesmo setup

O fluxo de identidade/workspace remoto foi implementado e qualificado: revisão humana, bootstrap parcial com chave exibida uma única vez, handoff autenticado, filhos R4, decisão canônica e Finish único. Revisões locais mantêm o bootstrap e o histórico, exigem nova confirmação material e recuperam um Finish anterior confirmado durante a revisão. Credencial atual, CAS e revogação continuam obrigatórios; nenhuma credencial administrativa chega ao host.

Pacotes não editáveis fora dos checkouts: **Nexus {counts['nexus']}/{counts['nexus']} e Connector {counts['connector']}/{counts['connector']} passaram**. Os {nexus['file_count']} arquivos Nexus e {connector['file_count']} Connector correspondem ao fonte/build/wheel/instalação. Core 0.0.14 inalterado. Os seis cenários conjuntos usam TCP/WSS reais e fixtures explícitas para instalação/provedor/cofre; não qualificam M1/M2 produtivos ou implantação em dois hosts. Falhas iniciais e retestes permanecem preservados, sem soma duplicada.

Connector commit/push: `{connector_commit}`. O plano e os conjuntos fixos de 59 tarefas, 132 cenários, 28 invariantes e 17 critérios permanecem iguais. PR-03, PR-10 integral e R3 continuam IN_PROGRESS; serviços nativos, provedores/clientes reais, renovação remota e regressão conjunta integral continuam pendentes. [Evidências e limites](plans/agent_ops/evidence/pr03-remote-bootstrap.md).
'''
with (ROOT / 'LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md').open('a', encoding='utf-8') as stream:
    stream.write(markdown)
with (ROOT / 'plans/agent_ops/implementation-report.md').open('a', encoding='utf-8') as stream:
    stream.write('\n\n## PR-03 — remote identity and reviewed setup\n\n' + summary +
        f"\n\nInstalled qualification: Nexus {counts['nexus']}, Connector {counts['connector']}; "
        f"{nexus['file_count']} and {connector['file_count']} exact package files respectively. Core unchanged. "
        'The six TCP/WSS cases preserve canonical authority and Finish, including local review and a racing prior commit. '
        'Source/installed counts and overlapping reruns remain separate. Initial failures, recovery limits, package hashes and rollback behavior are retained in '
        '[the milestone report](evidence/pr03-remote-bootstrap.md). Usage is documented in docs/remote-project-setup.md. '
        'No native service, real provider, personal credentials, registry publication or merge was used.\n')
print(json.dumps(dict(counts=counts, connector_commit=connector_commit, scope_unchanged=True, full_r3_complete=False)))
