"""Pure preparation: extract complete protocol fixture, never launch it."""
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
source_path=REPO/'tests/execution_r4/test_canonical_native_protocol_regressions.py'
source=source_path.read_text(encoding='utf-8')
node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='install_native')
full=ast.get_source_segment(source,node)
# The complete launch/guard/birth/containment implementation is retained. Only
# opt into native requests in the synthetic peer, under reviewed fixture policy.
assert full.count('            peers.append(peer)')==1
full=full.replace('            peers.append(peer)','            peer.native_approvals_enabled = True\n            peers.append(peer)')
assert full.count('env=environment or {}')==1
full=full.replace('env=environment or {}',"env={**(environment or {}), 'HST_SESSION_ID': session_id}")
fake_path=REPO/'tests/test_harness_codex_connector.py'
fake_text=fake_path.read_text(encoding='utf-8')
fake_node=next(n for n in ast.parse(fake_text).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_FAKE_SERVER_SOURCE' for t in n.targets))
fake=ast.literal_eval(fake_node.value)
helper='import asyncio\nimport json\nimport sys\nimport time\n\n'+full+'\n\nBASE_SOURCE='+repr(fake)+'\n'
ast.parse(helper)
(HERE/'protocol_fixture.py.txt').write_text(helper,encoding='utf-8')
pins={str(p.relative_to(REPO)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in [source_path,fake_path,
 REPO/'tests/execution_r4/test_canonical_native_inputs.py',REPO/'tests/execution_r4/test_canonical_native_approvals.py',
 REPO/'tests/execution_r4/test_operator_runtime.py',REPO/'tests/home_states/test_operational_sqlite.py',REPO/'tests/home_states/test_operational_board.py']}
(HERE/'preparation-pins.json').write_text(json.dumps(dict(pins=pins,helper_sha256=hashlib.sha256(helper.encode()).hexdigest(),
 difference='Enable native requests on synthetic peer; add owner-provided session ID for non-secret output marker. No guard/birth/protocol handling removed.',executed=False),indent=2)+'\n')
print(json.dumps(dict(status='PREPARED_NOT_EXECUTED',helper_sha256=hashlib.sha256(helper.encode()).hexdigest())))
