"""Read only the explicitly owned DX04 artifacts/code/DB; curate public projections."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import sqlite3

SOURCE = Path(r'C:/Users/jpamb/AppData/Local/Temp/dx04-native-launch-probe-l3gc2mp1')
DEST = Path(__file__).parent / 'public'
DEST.mkdir(exist_ok=False)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(relative, document):
    path = DEST / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')


copies = {
    'runners/runner-v1.py': SOURCE / 'failure-001-snapshot/dx04_probe.py',
    'runners/runner-v2.py': SOURCE / 'dx04_probe.py',
    'runners/restart-fixture.py': SOURCE / 'test_service_restart_contracts.py',
    'runners/console-diagnostic-v1.py': SOURCE / 'console_diagnostic.py',
    'runners/console-diagnostic-v2.py': SOURCE / 'console_diagnostic_v2.py',
    'diagnostics/initial-benign.json': SOURCE / 'diagnostic-v2/initial-benign.json',
    'diagnostics/fixed-benign.json': SOURCE / 'diagnostic-v2/fixed-benign.json',
    'diagnostics/runner-v2.patch': SOURCE / 'diagnostic-v2/runner-v2.patch',
    'diagnostics/ruff-v2.txt': SOURCE / 'diagnostic-v2/ruff.txt',
    'diagnostics/diagnostic-v2.md': SOURCE / 'DIAGNOSTIC-v2.md',
    'preflight/pywin32.json': SOURCE / 'preflight.json',
    'preflight/packages-before.json': Path(r'C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/dx04-preflight.json'),
    'reviews/runner-v2.json': Path(r'C:/Users/jpamb/AppData/Local/Temp/r3-dx04-v2-readonly-review-fq44_vl_/readonly-review.json'),
    'reviews/run-002.json': Path(r'C:/Users/jpamb/AppData/Local/Temp/r3-dx04-run002-readonly-review-mfz7__1t/readonly-review.json'),
    'audit/curate_postmortem.py': Path(__file__),
}
assert sha(copies['runners/runner-v1.py']) == '9bf238a2f0088ddf65259da61bfd27004fb0afd35cfed823e556215aec0c91ea'
assert sha(copies['runners/runner-v2.py']) == '80153ab8e8701299730e4144513506c65f6f078423abc4e9309d2198b167c34e'
assert sha(copies['reviews/runner-v2.json']) == 'd66ebf5d03a3ce7f889c6f42de16fe1122d83edd3834493537946fb9217dad3e'
assert sha(copies['reviews/run-002.json']) == '672a56b0fea06670d898381304861c9171395355be2fff9d5a4a93adc3eb7cb8'
for run in ('run-001', 'run-002'):
    for name in ('result.json', 'mcp-observations.jsonl'):
        copies[f'runs/{run}/{name}'] = SOURCE / run / name
    copies[f'runs/{run}/owner-proofs.json'] = SOURCE / run / 'server/owner-proofs.json'
for name in ('screen-labels.json', 'tty-owner.json', 'tty-child.json', 'watcher-error.json', 'worker-stage.json'):
    copies[f'runs/run-002/{name}'] = SOURCE / 'run-002' / name
original_hashes = {}
for relative, source in copies.items():
    target = DEST / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    assert sha(source) == sha(target)
    original_hashes[str(source)] = sha(source)

post = {'kind': 'read_only_postmortem', 'observed_at': datetime.now(timezone.utc).isoformat(),
        'status': 'UNCONFIRMED', 'aggregate_cleanup_confirmed': False,
        'native_retries_during_postmortem': 0, 'new_vault_accesses': 0, 'runs': {}}
hash_cache = {}
for run in ('run-001', 'run-002'):
    run_root = SOURCE / run
    result = json.loads((run_root / 'result.json').read_text())
    assert result['status'] == 'UNCONFIRMED'
    checks = []
    for name, expected in result['input_hashes_before'].items():
        path = Path(name)
        assert path.suffix in ('.py', '.exe'), 'Only recorded executable/code inputs may be hashed'
        current = hash_cache.setdefault(name, sha(path))
        row = {'original_path': name, 'before_sha256': expected,
               'current_sha256': current, 'current_matches_before': current == expected}
        if run == 'run-001' and path.name == 'dx04_probe.py':
            retained = copies['runners/runner-v1.py']
            row.update(retained_artifact='runners/runner-v1.py', retained_sha256=sha(retained),
                       retained_matches_before=sha(retained) == expected,
                       explanation='Current runner is the intentionally corrected V2; exact V1 retained.')
        checks.append(row)
    profiles = run_root / 'participant-home/terminal/participants'
    paths = list(profiles.glob('*.launch.json'))
    assert len(paths) == 1
    launch = json.loads(paths[0].read_text())
    setup = json.loads(paths[0].with_name(paths[0].name.replace('.launch.json', '.json')).read_text())
    expected_agent = setup['review']['context']['agent_id']
    expected_workspace = setup['review']['context']['workspace']['workspace_id']
    projection = {'state': launch['state'], 'pid_hint': launch.get('pid_hint'),
                  'basis': 'Read of the retained own launch checkpoint; PID hint grants no process authority.',
                  'raw_checkpoint_copied': False}
    write(f'runs/{run}/launch-checkpoint-projection.json', projection)
    database = (run_root / 'server/server-home/nexus.db').resolve(strict=True)
    assert database.is_relative_to(run_root.resolve())
    tables = ('agents', 'workspaces', 'sessions', 'messages', 'handoffs',
              'execution_bindings', 'execution_sessions', 'execution_operations', 'execution_receipts')
    connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
    try:
        connection.execute('PRAGMA query_only=ON')
        counts = {table: connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] for table in tables}
        identity = connection.execute('SELECT COUNT(*) FROM agents WHERE agent_id=?', (expected_agent,)).fetchone()[0]
        workspace = connection.execute('SELECT COUNT(*) FROM workspaces WHERE workspace_id=?', (expected_workspace,)).fetchone()[0]
    finally:
        connection.close()
    final_state = {'read_mode': 'SQLite mode=ro and query_only=ON', 'table_counts': counts,
        'expected_synthetic_agent_count': identity, 'expected_synthetic_workspace_count': workspace,
        'before_snapshot_retained': False, 'unchanged_claim': 'NOT_ESTABLISHED',
        'limit': 'Only final counts are retained. Empty work/session tables show no such surviving rows; this is not a byte-for-byte or before/after preservation proof. Authentication/access timestamps are not compared. No credential columns or other DBs were read; DB not copied or hashed.'}
    write(f'runs/{run}/canonical-final-counts.json', final_state)
    rows = [json.loads(line) for line in (run_root / 'mcp-observations.jsonl').read_text().splitlines() if line.strip()]
    entry = {'launch_checkpoint': projection, 'input_hash_comparisons': checks,
        'all_current_inputs_match_before': all(row['current_matches_before'] for row in checks),
        'all_inputs_matched_current_or_retained': all(row['current_matches_before'] or row.get('retained_matches_before') for row in checks),
        'mcp_observation_count': len(rows), 'mcp_statuses': [row['http_status'] for row in rows],
        'accepted_initialize_count': sum(row.get('method') == 'initialize' and row.get('protocol_result') is True and row.get('http_status') == 200 for row in rows),
        'accepted_tools_list_count': sum(row.get('method') == 'tools/list' and row.get('tools_count', 0) > 0 and row.get('http_status') == 200 for row in rows),
        'canonical_final_counts': final_state,
        'server_listener_closed_reported': result.get('server_listener_closed'),
        'own_vault_absent_after_reported': result.get('own_vault_absent_after'),
        'aggregate_cleanup_confirmed_retained': result.get('cleanup_confirmed'),
        'original_status': result['status'], 'original_errors': result['errors']}
    post['runs'][run] = entry
post['interpretation'] = {
    'run_001': 'Harness TypeError at CreateJobObject before CreateProcess; retained launch checkpoint remains review. Own Server/vault cleanup is reported, without an aggregate successful execution.',
    'run_002': 'Fixed login labels were observed; no accepted initialize/tools-list was recorded. Watcher failed with PermissionError and the own Job was terminated with exit125 and active0. This is a limited observation in this attempt, not a general causal claim that login or inference always precedes MCP.',
    'watcher_error_cause': 'UNKNOWN: only PermissionError class is retained; no new diagnosis or repair attempted.',
    'preflight': 'packages-before.json is the original prior verification summary (691/166/124 package files), not a retained file-by-file proof. Post-hashes check only the exact inputs listed in input_hashes_before.',
    'status': 'Keep UNCONFIRMED and aggregate cleanup false; do not promote DX04, native MCP, M1, or provider readiness.'}
write('audit/postmortem.json', post)
(DEST / 'README.md').write_text('''# DX04: curadoria finita das duas tentativas

Status preservado: **UNCONFIRMED**. Não houve nova execução de CLI nativa, Server ou cofre nesta auditoria.

`runs/run-001/result.json` e `runs/run-002/result.json` são os bytes originais. A primeira falha foi o TypeError do harness antes de CreateProcess; seu checkpoint continua review. A segunda observou os rótulos fixos de login, mas nenhum initialize/tools/list aceito: a única observação MCP é o controle negativo401. O watcher registrou PermissionError, sem causa determinada. O Job próprio foi encerrado forçadamente125/active0; os relatórios preservam listener fechado e cofre próprio ausente. Esses fatos individuais não se tornam cleanup_confirmed=true agregado.

O diagnóstico benigno V2 confirma somente console/TTY/Job/cleanup com `--help`; não substitui a cadeia nativa. Os runners V1/V2, delta único, diagnóstico inicial, revisões independentes e preflights estão separados. `preflight/packages-before.json` é um registro resumido da verificação anterior (691/166/124 arquivos), sem inventar uma tabela de provas file-by-file ausente.

`audit/postmortem.json` compara todos os inputs registrados. No run001 o runner atual é V2; o hash original é comprovado pela cópia V1 preservada. As projeções de checkpoint contêm somente state/pid_hint. As leituras SQLite próprias retêm apenas contagens finais e presença da identidade/workspace sintéticos. Não há baseline canônico retido: não se alega preservação antes/depois, nem comparação de timestamps de autenticação.

A observação de login sem MCP vale para esta tentativa/versão/contexto. Não estabelece uma regra universal sobre ordem de startup, nem torna inferência um requisito normativo.

Copiar estritamente `artifact-manifest.json.files`. A pasta pública contém somente os payloads listados e o manifesto. Homes, DBs, configs, credenciais, logs de Server/nativo, screenshots brutos e arquivos pending não foram copiados. Nenhum DB ou segredo foi hasheado. A leitura de cofre não foi repetida; sua ausência é o fato reportado pelos runners originais.
''', encoding='utf-8')
# Public review: no raw nxs_ key-shaped token. No runtime secret is read for comparison.
for path in DEST.rglob('*'):
    if path.is_file():
        assert not re.search(rb'nxs_[A-Za-z0-9_-]{40,}', path.read_bytes()), str(path)
for source, original in original_hashes.items():
    assert sha(source) == original, 'Source artifact changed during curation'
files = {str(path.relative_to(DEST)).replace('\\', '/'): {'sha256': sha(path), 'bytes': path.stat().st_size}
         for path in sorted(DEST.rglob('*')) if path.is_file()}
manifest = {'schema_version': 1, 'kind': 'dx04_native_launch_postmortem_public_allowlist',
            'status': 'UNCONFIRMED', 'aggregate_cleanup_confirmed': False, 'files': files,
            'exclusions': ['homes', 'DBs', 'private configs', 'credentials or credential hashes',
                           'raw console text/screenshots', 'Server/native logs', 'pending files', '__pycache__']}
write('artifact-manifest.json', manifest)
print(json.dumps({'public': str(DEST), 'payload_count': len(files),
                  'manifest_sha256': sha(DEST / 'artifact-manifest.json'),
                  'run_001_inputs_matched_current_or_retained': post['runs']['run-001']['all_inputs_matched_current_or_retained'],
                  'run_002_inputs_current_match': post['runs']['run-002']['all_current_inputs_match_before'],
                  'checkpoint_states': {run: row['launch_checkpoint']['state'] for run, row in post['runs'].items()},
                  'final_counts': {run: row['canonical_final_counts']['table_counts'] for run, row in post['runs'].items()}}))
