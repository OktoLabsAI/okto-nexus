"""Static public-DTO counterpart; preserve first failed cut and scripts."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(HERE/'themes.js')=='f5d0c1176b31a8974e0c329e439840e1830ff89207629647a1d006f776c70f17'
sample=HERE/'runs/hst-native-zoom-r9-themes-1/control/exp-active.json'
board=json.loads(sample.read_text())['board']
assert board['presentation_version']==2 and 'operational_sessions' not in board['source_status']
cards=[v for p in board['columns'].values()for v in p['items']if v['kind']=='harness']
assert len(cards)==2 and {v['operational_status']['activity']for v in cards}=={'working','idle'}
preflight=dict(status='STATIC_CAPTURED_PUBLIC_DTO_REVIEW',source=sample.relative_to(REPO).as_posix(),source_sha256=sha(sample),presentation_version=board['presentation_version'],public_source_status=board['source_status'],internal_operational_source_key_absent=True,operational_status_keys=sorted(cards[0]['operational_status']),captured_operational_values=[dict(activity=v['operational_status']['activity'],freshness=v['operational_status']['freshness'])for v in cards],unknown_shape='Same public operational_status fields; expected unknown/unavailable is a future runtime assertion, not executed evidence')
(HERE/'preflight-public-shapes.json').write_text(json.dumps(preflight,indent=2)+'\n')
js=(HERE/'themes.js').read_text()
old="actual=page.__i04Boards.find(v=>v.at>=start&&v.presentation_version===2&&(cfg.phase==='known'?v.source_status.operational_sessions==='ready':v.source_status.operational_sessions==='unavailable'));"
new="""actual=page.__i04Boards.find(v=>{
          if(v.at<start||v.presentation_version!==2)return false;
          const items=Object.values(v.columns).flat(),a=items.find(i=>i.id===cfg.aCard),b=items.find(i=>i.id===cfg.bCard);
          return cfg.phase==='known'?a?.status?.activity==='working'&&b?.status?.activity==='idle'&&a.status.freshness==='current'&&b.status.freshness==='current':a?.status?.activity==='unknown'&&b?.status?.activity==='unknown'&&a.status.freshness==='unavailable'&&b.status.freshness==='unavailable';
        });"""
assert js.count(old)==1;js=js.replace(old,new)
(HERE/'themes-v2.js').write_text(js)
builder=(HERE/'reader_builder.py').read_text()
old="""                        exp['theme_rows_original']=query._rows
                        def fail_operational_rows(uow,sql,params,check_budget=None):
                            if sql==theme_facts.SESSIONS:
                                raise sqlite3.OperationalError('Own fixture operational fact reader unavailable')"""
new="""                        exp['theme_rows_original']=query._rows
                        exp['theme_fault_audit']=dict(sql_sha256=hashlib.sha256(theme_facts.SESSIONS.encode()).hexdigest(),hits=0,started_at=deps.clock.now_iso(),restored=False)
                        write('theme-facts-fault-audit.json',exp['theme_fault_audit'])
                        def fail_operational_rows(uow,sql,params,check_budget=None):
                            if sql==theme_facts.SESSIONS:
                                exp['theme_fault_audit']['hits']+=1
                                exp['theme_fault_audit']['last_hit_at']=deps.clock.now_iso()
                                raise sqlite3.OperationalError('Own fixture operational fact reader unavailable')"""
assert builder.count(old)==1;builder=builder.replace(old,new)
anchor="                        exp_snapshot('theme-unknown')"
assert builder.count(anchor)==1;builder=builder.replace(anchor,anchor+"\n                        write('theme-facts-fault-audit.json',exp['theme_fault_audit'])")
old="""                        patch.setattr(app.state.home_entries.queries,'_rows',exp.pop('theme_rows_original'))
                        exp_snapshot('theme-restored')"""
new="""                        patch.setattr(app.state.home_entries.queries,'_rows',exp.pop('theme_rows_original'))
                        exp['theme_fault_audit'].update(restored=True,restored_at=deps.clock.now_iso())
                        write('theme-facts-fault-audit.json',exp['theme_fault_audit'])
                        exp_snapshot('theme-restored')"""
assert builder.count(old)==1;builder=builder.replace(old,new)
ast.parse(builder);(HERE/'reader_builder_v2.py').write_text(builder)
runner=(HERE/'run.py').read_text().replace("HERE/'prepared-themes.json'","HERE/'prepared-themes-v2.json'").replace("HERE/'reader_builder.py'","HERE/'reader_builder_v2.py'").replace("'themes.js'","'themes-v2.js'")
old="        assert fault['board']['source_status']['operational_sessions']=='unavailable'"
new="""        fault_cards=[item for column in fault['board']['columns'].values()for item in column['items']if item['kind']=='harness'and item['id']in[exact['aCard'],exact['bCard']]]
        assert len(fault_cards)==2 and all(item['operational_status']['activity']=='unknown'and item['operational_status']['freshness']=='unavailable'for item in fault_cards)
        audit=json.loads((root/'control/theme-facts-fault-audit.json').read_text());assert audit['hits']>0 and not audit['restored']and audit['sql_sha256']==manifest['operational_sessions_sql_sha256']"""
assert runner.count(old)==1;runner=runner.replace(old,new)
ast.parse(runner);(HERE/'run_v2.py').write_text(runner)
curator=(HERE/'curate.py').read_text();anchor="'control/exp-theme-restored.json'";assert curator.count(anchor)==1
curator=curator.replace(anchor,anchor+",'control/theme-facts-fault-audit.json'")
ast.parse(curator);(HERE/'curate_v2.py').write_text(curator)
diff=''
for oldname,newname in [('themes.js','themes-v2.js'),('reader_builder.py','reader_builder_v2.py'),('run.py','run_v2.py'),('curate.py','curate_v2.py')]:
    diff+=''.join(difflib.unified_diff((HERE/oldname).read_text().splitlines(True),(HERE/newname).read_text().splitlines(True),fromfile=oldname,tofile=newname))
(HERE/'variant-v2.diff').write_text(diff)
manifest=json.loads((HERE/'prepared-themes.json').read_text())
facts=ast.parse((REPO/'src/okto_nexus/adapters/outbound/sqlite/home_operational_facts.py').read_text())
sql=next(ast.literal_eval(n.value)for n in facts.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='SESSIONS'for t in n.targets))
manifest['operational_sessions_sql_sha256']=hashlib.sha256(sql.encode()).hexdigest()
for name in ['themes-v2.js','reader_builder_v2.py','run_v2.py','curate_v2.py','prepare_v2.py','preflight-public-shapes.json','variant-v2.diff','variant-v2-notes.md','prepared-themes.json']:
    p=HERE/name;manifest['input_pins'][p.relative_to(REPO).as_posix()]=sha(p)
manifest['status']='I04_PUBLIC_OPERATIONAL_DTO_COUNTERPART_PREPARED_NOT_EXECUTED'
manifest['counterpart_changes']=['Captured R9 DTO keys validated before gate: no internal operational source key assumed','Known/unknown response predicates use actual public operational_status fields on same IDs','Fixture-only operational SQL fault hit count/hash audit, no DTO or authority mutation']
(HERE/'prepared-themes-v2.json').write_text(json.dumps(manifest,indent=2)+'\n')
gate=json.loads((HERE/'GATE.template.json').read_text());assert not gate['approved'];gate['manifest_sha256']=sha(HERE/'prepared-themes-v2.json');gate['cut_id']='hst-native-zoom-r9-themes-2'
(HERE/'GATE-v2.template.json').write_text(json.dumps(gate,indent=2)+'\n')
print(json.dumps(dict(status='PREPARED_NOT_EXECUTED',manifest_sha256=sha(HERE/'prepared-themes-v2.json'),files={n:sha(HERE/n)for n in ['run_v2.py','themes-v2.js','reader_builder_v2.py','variant-v2.diff']}),indent=2))
