from pathlib import Path
import hashlib
import json
import tempfile

here=Path(__file__).resolve().parent
root=here.parents[3]
prior=here.parent/'pr15-human-third-prepare'
pins=json.loads((prior/'manifest.json').read_text())
drift=[p for p,h in pins.items() if hashlib.sha256((prior/p).read_bytes()).hexdigest()!=h]
assert not drift,drift
(here/'pr15-manifest-copy.json').write_bytes((prior/'manifest.json').read_bytes())
source=(prior/'fixture.py').read_text(encoding='utf-8')
changes=[
 ('import pytest\n','import pytest\nfrom seed import prepare_r3,add_parallel\n'),
 ("prefix='nexus-ui043-third-'","prefix='nexus-r3-harness-'"),
 ('identities=seed_result(s,home);configure_inert_catalog(s,patch,home)','identities=seed_result(s,home);prepare_r3(s,identities);configure_inert_catalog(s,patch,home)'),
 ("permitted=method in{'GET','HEAD','OPTIONS'} or(method=='POST' and(path.endswith(allowed_suffixes) or path=='/api/v1/runtime-management/runtime/approval-decisions' or path.startswith('/api/v1/attention/') and path.endswith(('/seen','/unseen','/snooze','/unsnooze'))))", "permitted=method in{'GET','HEAD','OPTIONS'}"),
 ("last_renew=time.monotonic();last_inventory=0.0;fresh_published=False","last_renew=time.monotonic();last_inventory=0.0;fresh_published=False;parallel_added=False"),
 ("ws.send_text(encode_r4_frame(frame).decode())", "ws.send_text(encode_r4_frame(frame).decode())\n                        if not parallel_added and args.ready_file.with_name('add-parallel').exists():\n                            add_parallel(s);parallel_added=True\n                            args.ready_file.with_name('parallel-added.json').write_text(json.dumps({'at':s.clock.now_iso(),'helper':'add_parallel_running_read_fact','layer':'Synthetic schema-valid SQLite READ FACT; no new admission/native process.'}),encoding='utf-8')"),
 ("if not fresh_published and args.ready_file.with_name('publish-fresh-question').exists():", "if False:  # No fresh question is published in this read-only qualification."),
 ("Path(__file__),Path(__file__).with_name('observation_window.py'),", "Path(__file__),Path(__file__).with_name('observation_window.py'),Path(__file__).with_name('seed.py'),ROOT/'tests/ui_simplification/test_harness_board.py',"),
]
for before,after in changes:
    assert source.count(before)==1,before
    source=source.replace(before,after)
(here/'fixture.py').write_text(source,encoding='utf-8')
(here/'observation_window.py').write_bytes((prior/'observation_window.py').read_bytes())
out=root/'output/playwright/r3-harness-board'
out.mkdir(parents=True,exist_ok=True)
control=Path(tempfile.mkdtemp(prefix='nexus-r3-harness-control-'))
(out/'control.json').write_text(json.dumps({'control':str(control),'out':str(out)}),encoding='utf-8')
print(json.dumps({'control':str(control),'out':str(out),'prior_entries':len(pins),'prior_drift':drift,'processes_started':False}))
