"""One bounded SELECT-only projection of this campaign's native refusal."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import time

B = Path(__file__).resolve().parent
ROOT = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7')
W = ROOT / 'successor14/work-revision15'
DB = ROOT / 'campaign/nexus-home/nexus.db'
DECISION = 'r4decision_bd7e39ba9902581c61f44510052d5e30'
REQUEST = 'r4request_e133588fe9c28d66ac53353d1fedbde4f26e5c4607e382226d013500f0ad48c7'
SESSION = 'ses_86bf8a7f016fafe06e794ce5f0028611'
MESSAGE = 'Runtime action is not authorized.'


def pin(path):
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


started = time.monotonic()
c = sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True, timeout=1)
c.row_factory = sqlite3.Row
try:
    c.execute('PRAGMA query_only=ON')
    c.set_progress_handler(lambda: int(time.monotonic() - started > 2), 100)
    decision = dict(c.execute(
        'SELECT decision_id,canonical_request_id,native_operation_id,actor_agent_id,canonical_state,'
        'actor_guard_digest LIKE ? AS managed_input_v1,actor_guard_digest LIKE ? AS plain_agent_guard '
        'FROM execution_decisions WHERE decision_id=?',
        ('managed-input-v1:%', 'sha256:%', DECISION)).fetchone())
    assert decision['canonical_request_id'] == REQUEST
    op = decision['native_operation_id']
    operation = dict(c.execute(
        'SELECT operation_id,session_id,actor_agent_id,subject_agent_id,action '
        'FROM execution_operations WHERE operation_id=?', (op,)).fetchone())
    assert operation['session_id'] == SESSION
    outbox = c.execute('SELECT dispatch_state,last_error FROM execution_dispatch_outbox '
                       'WHERE operation_id=?', (op,)).fetchone()
    error = json.loads(outbox['last_error'])
    assert error['message'] == MESSAGE
    receipt_count = c.execute('SELECT count(*) FROM execution_receipts WHERE operation_id=?', (op,)).fetchone()[0]
    # Credential contents/hashes never leave SQLite; only presence is projected.
    actor = dict(c.execute('SELECT agent_id,is_active,'
        '(api_key_hash IS NOT NULL AND length(api_key_hash)>0) AS credential_present '
        'FROM agents WHERE agent_id=?', ('operator',)).fetchone())
finally:
    c.close()

installation = json.loads((W / 'package/installation.json').read_bytes())
prefix = Path(installation['python']).parents[1]
relative = ['application/execution_native_decisions.py', 'application/execution_input_authority.py',
            'application/runtime_access.py', 'application/execution_native_facts.py']
sources = []
for rel in relative:
    installed = prefix / 'Lib/site-packages/okto_nexus' / rel
    source = Path('D:/Projetos/Techridy/okto_labs_okto_nexus/src/okto_nexus') / rel
    sources.append(dict(installed=pin(installed), source=pin(source), bytes_equal=installed.read_bytes() == source.read_bytes()))

report = dict(
    kind='BOUNDED_READONLY_NATIVE_DECISION_REFUSAL_DIAGNOSIS',
    recorded_at_utc=datetime.now(timezone.utc).isoformat(),
    database_path=str(DB), database_open='mode=ro; query_only=ON; timeout1; progress deadline2',
    decision=decision, operation=operation, actor=actor,
    server_receipt_count=receipt_count,
    dispatch=dict(state=outbox['dispatch_state'], error={k:error[k] for k in ('code','stage','possible_effect','retry_safe')},
                  message=MESSAGE),
    recovered_public_receipt=pin(W / 'public' / (REQUEST + '-recovered-decision.json')),
    code=sources,
    causal_path=['validate_native_dispatch reconstructs every non-managed responder as agent_key.',
        'This committed decision has a plain agent guard and operator has no API-key credential.',
        'input_authority invokes access.authenticate before checking recorded guard.',
        'authenticate_runtime_facts rejects agent_key context without credential with the exact persisted message.'],
    limitations=['Server outbox/receipt evidence, not a raw Core journal or provider transcript.',
        'No approval replay, credential value/hash export, service mutation, force or provider operation.',
        'Canonical CONFIRMED records the human decision; it does not establish native delivery.'],
)
(B / 'diagnosis.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
files = [dict(path=p.name, sha256=pin(p)['sha256'], bytes=p.stat().st_size)
         for p in [B / 'observe.py', B / 'diagnosis.json']]
(B / 'public-allowlist.json').write_text(json.dumps(dict(files=files), indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(diagnosis=pin(B / 'diagnosis.json'), allowlist=pin(B / 'public-allowlist.json'),
                     source_installed_equal=[v['bytes_equal'] for v in sources])))
