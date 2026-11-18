"""Add sanitized new-cut artifacts without modifying any existing curator/cut."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from curation_privacy import cas_values,redact

HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def parse(path):
    text=path.read_text(encoding='utf-8').replace('\r\n','\n');raw=text.split('### Result\n',1)[1].split('\n###',1)[0].strip();return json.loads(raw)
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--tag',required=True);p.add_argument('--classification',required=True);p.add_argument('--verify-decision',action='store_true');a=p.parse_args()
    root=a.root.resolve();assert root.name.startswith('nexus-hst-browser-')and all(c.isalnum()or c in '-_'for c in a.tag)
    assert(root/'control/supervisor-cleanup.json').exists()
    if a.verify_decision:
        before=json.loads((root/'control/next-before.json').read_text());after=json.loads((root/'control/next-after.json').read_text());browser=parse(root/'cli-decision.txt')
        assert len(browser['posts'])==2 and sorted(x['status']for x in browser['posts'])==[202,409]
        accepted=next(x for x in browser['posts']if x['status']==202);request=accepted['request_id']
        assert not[x for x in before['decisions']if x['canonical_request_id']==request]
        rows=[x for x in after['decisions']if x['canonical_request_id']==request];assert len(rows)==1;row=rows[0]
        original=next(x for x in before['requests']if x['request_id']==request)['approval_key']
        for field in ['server_id','executor_id','binding_id','agent_id','workspace_id','session_id','session_owner_generation']:assert row[field]==original[field]
        assert row['client_intent_id']==accepted['client_intent_id']and row['actor_agent_id']=='operator'
        assert len(after['native_writes'])-len(before['native_writes'])==1
        assert len([x for x in after['native_writes']if x['operation_id']==row['native_operation_id']])==1
        assert before['productive_operations']==after['productive_operations']
        recovered=next(x for x in browser['checks']if x['id']=='recover-same-decision-and-native-operation');assert recovered['ok']and recovered['detail']['decision_id']==row['decision_id']and recovered['detail']['native_operation_id']==row['native_operation_id']
        assert next(x for x in browser['checks']if x['id']=='exact-request-and-session-on-receipt')['ok']
        receipts=after['receipts'][row['native_operation_id']];assert receipts
        observation=dict(status='PASS_CAPTURED_CANONICAL_INVARIANTS_WITH_BROWSER_ORACLE_LIMIT',posts=browser['posts'],decision_count=1,native_write_count=1,decision_id=row['decision_id'],client_intent_id=row['client_intent_id'],native_operation_id=row['native_operation_id'],receipt_count=len(receipts),receipts=receipts,operator_and_full_tuple_preserved=True,no_new_productive_operation=True,limit='Original-intent-preserved browser assertion inspected only Home sessionStorage although either context could win. Winner storage not captured; not inferred. Both explicit Check actions and canonical GET receipt occurred before that failed assertion. Original browser FAIL preserved.')
        (root/'next-captured-host-invariants.json').write_text(json.dumps(observation,indent=2)+'\n')
    subprocess.run([sys.executable,'-B',str(HERE/'curate.py'),'--root',str(root),'--tag',a.tag,'--classification',a.classification],check=True)
    dest=HERE/'nextcuts'/a.tag;assert not dest.exists();dest.mkdir(parents=True)
    cookies=[x['value'].encode()for x in json.loads((root/'control/browser-storage.private.json').read_text())['cookies']]
    names=['next-builder-proof.json','next-run-failure.json','next-host-invariants.json','next-captured-host-invariants.json','next-payload-proof.json','next-steps.json','control/next-before.json','control/next-after.json','control/next-arrival.json','next-decision.js','next-context.js','next-context-finish.js']
    names += [p.name for pattern in ['next-context-page.js','next-invalid.js','next-dirty.js','history-*.js']for p in root.glob(pattern)]
    entries=[];cas=cas_values(root)
    for name in names:
        p=root/name
        if not p.exists():continue
        raw,count=redact(p.read_bytes(),cas);assert not any(secret in raw for secret in cookies)
        target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        entries.append(dict(path=name,sha256=sha(target),source_sha256=sha(p),bytes=len(raw),cas_redactions=count))
    q=HERE/'cuts'/a.tag/'qualification.json';manifest=dict(classification=a.classification,base_cut='../../cuts/'+a.tag,base_qualification_sha256=sha(q),copies=entries,credentials='Private cookie/storage/wire not copied; exact fixtureCAS redacted',active_resources=False)
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(supplement=str(dest),copies=len(entries),manifest_sha256=sha(dest/'manifest.json'))))
if __name__=='__main__':main()
