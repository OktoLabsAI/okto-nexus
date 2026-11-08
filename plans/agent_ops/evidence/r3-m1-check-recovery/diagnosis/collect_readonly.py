"""Metadata-only projection of the stopped M1 v8 campaign; never imports products."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

OUT = Path(__file__).parent
CAMPAIGN = Path('C:/Users/jpamb/AppData/Local/Temp/m1-fresh-v8-pg0b6zbf/campaign')
HOME = CAMPAIGN / 'nexus-home'
INSTALLED = Path('C:/Users/jpamb/AppData/Local/Temp/m1-base06-install-g9ii2zhe/venv/Lib/site-packages')
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
CORE = Path('D:/Projetos/Techridy/okto-nexus-connector-core')
def stamp(p):
    raw = p.read_bytes()
    return dict(path=str(p), bytes=len(raw), sha256=sha256(raw).hexdigest(),
        mtime_utc=datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat())

profile_path = HOME / 'terminal/profiles/m1v8-local.json'
profile = json.loads(profile_path.read_text(encoding='utf-8'))
request = profile['request']
selector = request['candidate_ref']
projection = dict(format='m1_readonly_installation_check_diagnosis', revision=1,
    captured_at=datetime.now(timezone.utc).isoformat(),
    profile=dict(state=profile['state'], server_id=profile['server_id'],
        version_check_required=profile.get('version_check_required'),
        version_check_confirmed=profile.get('version_check_confirmed'),
        request={k:request.get(k) for k in ('client_intent_id', 'agent_id', 'executor_id',
                                          'workspace_id', 'candidate_ref', 'inventory_revision')},
        result_present='result' in profile, test_present='test' in profile,
        file=stamp(profile_path)))

def codex_rows(v):
    rows=[]
    if isinstance(v,dict):
        if v.get('candidate_ref') == selector:
            rows.append({k:v[k] for k in ('adapter_id','candidate_ref','version','trust','state') if k in v})
        for value in v.values():
            rows.extend(codex_rows(value))
    elif isinstance(v,list):
        for value in v:
            rows.extend(codex_rows(value))
    return rows

db=HOME/'nexus.db'
before=stamp(db)
with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row
    conn.execute('BEGIN')
    projection['local_observations']=[dict(r) for r in conn.execute(
        'SELECT server_id,executor_id,candidate_ref,core_version,platform,version,actor_agent_id,observed_at '
        'FROM execution_local_observations WHERE executor_id=? AND candidate_ref=?',
        (request['executor_id'],selector))]
    projection['counts']={t:conn.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in
        ('execution_operations','execution_receipts','execution_sessions','connection_setup_commits')}
    projection['inventory_snapshots']=[]
    for row in conn.execute('SELECT publication_sequence,inventory_revision,received_at,observation_age_ms,'
        'canonical_projection FROM execution_inventory_snapshots WHERE executor_id=? ORDER BY publication_sequence',
        (request['executor_id'],)):
        item=dict(row)
        item['selected_metadata']=codex_rows(json.loads(item.pop('canonical_projection')))
        projection['inventory_snapshots'].append(item)
    conn.rollback()
after=stamp(db)
projection['database']=dict(before=before,after=after,unchanged=before['sha256']==after['sha256'],mode='ro')

stdout=CAMPAIGN/'private/local-setup.stdout'
value=json.loads(stdout.read_text(encoding='utf-8-sig'))
projection['cli']={k:value.get(k) for k in ('state','code','message','possible_effect')}
projection['files']=[stamp(p) for p in (stdout,CAMPAIGN/'public/local-setup-result.json',
    CAMPAIGN/'public/lifecycle-nexus-stop-result.json')]
projection['timing_limit']='File mtimes are supporting evidence, not a retained per-HTTP timing trace.'
projection['sources']=[]
for relative in ('application/terminal_connection.py','adapters/outbound/terminal_http.py',
                 'bootstrap/embedded_inventory.py','application/execution_local_observations.py',
                 'adapters/inbound/http/runtime_v1.py'):
    source=stamp(REPO/'src/okto_nexus'/relative)
    installed=stamp(INSTALLED/'okto_nexus'/relative)
    projection['sources'].append(dict(relative=relative,source=source,installed=installed,
        bytes_equal=source['sha256']==installed['sha256']))
relative='inventory_observer.py'
source=stamp(CORE/'src/nexus_connector_core'/relative)
installed=stamp(INSTALLED/'nexus_connector_core'/relative)
projection['sources'].append(dict(relative='nexus_connector_core/'+relative,source=source,installed=installed,
    bytes_equal=source['sha256']==installed['sha256']))
projection['effects']=dict(product_imports=False,http_requests=False,sqlite_writes=False,
    replay=False,provider=False,service=False,private_raw_payloads_retained=False)
with (OUT/'diagnosis.json').open('x',encoding='utf-8',newline='\n') as f:
    json.dump(projection,f,ensure_ascii=False,indent=2)
    f.write('\n')
print(json.dumps({'diagnosis':stamp(OUT/'diagnosis.json'),
                  'all_installed_sources_match':all(r['bytes_equal'] for r in projection['sources']),
                  'database_unchanged':projection['database']['unchanged']}))
