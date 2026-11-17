"""Derive only captured invariants; never rerun a native/browser operation."""
import argparse
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve()
    assert root.name.startswith('nexus-hst-browser-')
    cleanup=json.loads((root/'control/supervisor-cleanup.json').read_text());assert cleanup['exit_code']is not None and not cleanup['remaining_known_births']
    final=json.loads((root/'control/final.json').read_text());rows=final['requests']
    native='/api/v1/runtime-management/runtime/approval-decisions'
    posts=[r for r in rows if r['method']=='POST'];assert len(posts)==2 and all(r['path']==native for r in posts)and sorted(r['status']for r in posts)==[202,409]
    captured=json.loads((root/'next-captured-host-invariants.json').read_text());decision=captured['decision_id']
    gets=[r for r in rows if r['method']=='GET'and r['path']==native+'/'+decision];assert len(gets)>=2 and all(r['status']==200 for r in gets)
    assert captured['decision_count']==1 and captured['native_write_count']==1 and captured['no_new_productive_operation']and captured['operator_and_full_tuple_preserved']
    result=dict(status='OFFLINE_ASSERTIONS_FROM_COMPLETED_CAPTURE_ONLY',source_root=str(root),all_browser_post_count=len(posts),post_statuses=[r['status']for r in posts],same_decision_get_count=len(gets),same_decision_get_statuses=[r['status']for r in gets],decision_id=decision,accepted_client_intent_id=captured['client_intent_id'],native_operation_id=captured['native_operation_id'],decision_count=1,native_write_count=1,receipt_count=captured['receipt_count'],receipt_stages=[r['stage']for r in captured['receipts']],no_new_productive_operation=True,recovery_no_additional_post_observed=True,full_tuple_and_operator_preserved=True,original_browser_oracle='FAIL_RETAINED_HOME_NOT_NECESSARILY_WINNER',winner_session_storage='NOT_CAPTURED',honest_application_text_assertion='NOT_RUN_AFTER_PRIOR_ORACLE_ABORT',get_attribution='Script performed two explicit Check clicks, but GET capture is not context/initiator labeled; automatic polling may also contribute. No per-context GET attribution claimed.',transport='Two browser submissions overlap; transport holds second POST until first canonical acceptance. Not a simultaneous database-transaction claim.',inputs={name:hashlib.sha256((root/name).read_bytes()).hexdigest()for name in ['control/final.json','control/next-before.json','control/next-after.json','cli-decision.txt','next-captured-host-invariants.json']})
    dest=HERE/'nextcuts/r7-decision-offline-derivative';assert not dest.exists();dest.mkdir()
    out=dest/'qualification.json';out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(path=str(out),posts=len(posts),same_receipt_gets=len(gets),sha256=hashlib.sha256(out.read_bytes()).hexdigest())))
if __name__=='__main__':main()
