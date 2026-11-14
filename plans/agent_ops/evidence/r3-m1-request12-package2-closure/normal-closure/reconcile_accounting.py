"""Exact request12 post-exit metadata reconciliation. No Controller or writes to DB."""
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
B = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7')
W = B / 'successor14/work-request12-package2'
RID = 'm1v14-local-work-12'
SID = 'ses_7c8b77c2988e1645a0c9b6aefd6d80bc'
OP = 'op_81de2e90997c1689eb0ec2aaff00e5fb'
INTERRUPT = 'op_851b83130e83385e1dc2eb47bfe06452'
CP_SHA = '70826adc11d41aba2ed84b56e8b673e0f8153d5a550c1d34ec7abfce515c5c37'

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())
def require(ok, code):
    if not ok: raise ValueError(code)
def pin(path): return {'path': str(path), 'sha256': sha(path)}
def write(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write('\n')

def main():
    checkpoint = W / 'private/controller.json'
    require(sha(checkpoint) == CP_SHA, 'ORIGINAL_CHECKPOINT_CHANGED')
    freeze = W / 'runtime-freeze.json'
    require(sha(freeze) == '9706592bce4b58cf7b95bcf5fb60e682c28f1542c12b68f731a7e9f501e8e96b', 'FREEZE_CHANGED')
    for item in read(freeze)['files'].values():
        require(sha(item['path']) == item['sha256'], 'FROZEN_SOURCE_CHANGED')
    physical_path = W / 'public/nexus-exit-proof.json'
    physical = read(physical_path)
    expected = {'parent': (25360,134391640831034171), 'launcher': (9960,134391641007486054),
                'child': (5924,134391641008089611)}
    require(physical['generation'] == '3f322a5e7874bdca13a6c4d2cd4f6435'
            and physical['retained_handle'] is True and physical['exit_confirmed'] is True
            and physical['force_used'] is False, 'PHYSICAL_EXIT_REQUIRED')
    for name, (pid,birth) in expected.items():
        item = physical['processes'][name]
        require(item['pid'] == pid and item['birth_filetime'] == birth and item['physical_exit_confirmed']
                and item['exit_code'] == 0 and not item['terminate_right'], 'COHORT_EXIT_REQUIRED')
    presence_path = W / 'public/final-presence.json'
    presence = read(presence_path)
    require(presence['status'] == 'NORMAL_CLEANUP_CONFIRMED'
            and all(t['absent'] for t in presence['tasks'].values()), 'FINAL_PRESENCE_REQUIRED')
    sys.path.insert(0, str(W / 'modules'))
    import token_collector as tokens
    from independent_journal import CanonicalIntentReader, CoreJournalReader
    from legacy_controller import seal
    before = read(checkpoint)
    require(before['state_sha256'] == seal(before), 'CHECKPOINT_SEAL_INVALID')
    require(set(before['requests']) == {RID}, 'REQUEST_SET_CHANGED')
    record = before['requests'][RID]
    require(record['session'] == SID and record['operation'] == OP and not record['settled'], 'REQUEST_CHANGED')
    require(before['policy']['carry_in_tokens'] == 272648 and before['policy']['carry_in_admissions'] == 11, 'BASELINE_CHANGED')
    state = tokens.restore(before['collector'])
    original_summary = tokens.summary(state)
    home = B / 'campaign/nexus-home'
    reader = CanonicalIntentReader(B, home, server_id=record['scope']['server_id'],
                                   actor_id=record['actor_agent_id'], pre_scope=record['scope'])
    journal = CoreJournalReader(B, home, 'local')
    started = time.monotonic()
    def bound(): require(time.monotonic() - started < 30, 'POST_EXIT_READ_TOTAL_BOUND')
    reader.io.aggregate_check = bound
    journal.io.aggregate_check = bound
    try:
        canonical = reader.read(RID)
        require(canonical and canonical['operation_id'] == OP and canonical['scope']['session_id'] == SID, 'CANONICAL_SCOPE_CHANGED')
        scope = canonical['scope']
        require(all(scope[k] == v for k,v in record['scope'].items()), 'SCOPE_CHANGED')
        pages = []
        for _ in range(20):
            cursor = state['streams'][record['stream']]['cursor']
            page = journal.read(scope, cursor)
            require(page and page['stream_epoch'] == canonical['session_state']['stream_epoch'], 'STREAM_CHANGED')
            state = tokens.bind_operation(state, request_id=RID, operation_id=OP)
            state = tokens.observe(state, stream=record['stream'], after_sequence=cursor, page=page)
            pages.append({'after_sequence': cursor, 'event_count': page['count'],
                          'next_after_sequence': page['next_after_sequence'], 'committed_contiguous': page['committed_contiguous'],
                          'has_more': page['has_more'], 'projection_sha256': tokens.fingerprint(page)})
            if not page['has_more']: break
        else: raise ValueError('BOUNDED_CATCHUP_INCOMPLETE')
        key = tuple(scope[k] for k in ('server_id','executor_id','session_id'))
        with reader.io.open(reader.database) as db:
            native = [dict(row) for row in db.execute('SELECT canonical_request_id,source_operation_id,source_sequence,kind,request_revision,state FROM execution_native_requests WHERE server_id=? AND executor_id=? AND session_id=? LIMIT 20', key)]
            interrupt_operation = db.execute('SELECT operation_id,session_id,action,admission_state FROM execution_operations WHERE server_id=? AND executor_id=? AND session_id=? AND operation_id=?', (*key,INTERRUPT)).fetchone()
            interrupt_receipt = db.execute('SELECT stage,error_code,possible_effect,retry_safe,receipt_revision FROM execution_receipts WHERE server_id=? AND executor_id=? AND operation_id=? ORDER BY receipt_revision DESC LIMIT 1', (*key[:2],INTERRUPT)).fetchone()
        with journal.io.open(journal.path(scope)) as db:
            core_operations = [dict(row) for row in db.execute('SELECT operation_id,stage,possible_effect,retry_safe,native_id,error_code FROM operations_v2 WHERE server_id=? AND executor_id=? AND session_id=? AND operation_id IN (?,?)', (*key,OP,INTERRUPT))]
            active_slots = db.execute('SELECT count(*) FROM owned_slot_reservations WHERE server_id=? AND executor_id=? AND session_id=? AND released=0', key).fetchone()[0]
        summary = tokens.summary(state)
        stream = state['streams'][record['stream']]
        components = state['threads'][stream['thread']]['components']
        settled = state['requests'][RID]['state'] == 'settled_observed'
        require(settled and canonical['operation_receipt']['stage'] in ('CANCELLED','FAILED','SUCCEEDED'), 'TERMINAL_UNCONFIRMED')
        require(canonical['session_state']['lifecycle_state'] == 'CLOSED' and canonical['session_state']['lease_state'] == 'CLOSED', 'SESSION_NOT_CLOSED')
        require(not any(row['state'] == 'PENDING' for row in native) and active_slots == 0, 'PENDING_OR_SLOT_REMAINS')
        require(sha(checkpoint) == CP_SHA, 'ORIGINAL_CHANGED_DURING_READ')
        evidence = {'kind': 'POST_EXIT_READONLY_ACCOUNTING_COMPANION_NOT_CONTROLLER', 'request_id': RID,
            'original_checkpoint': pin(checkpoint), 'original_faults': before['faults'], 'original_request_settled': False,
            'original_checkpoint_untouched': True, 'original_observed_increment': original_summary['known_observed_tokens'],
            'canonical': canonical, 'interrupt_operation': dict(interrupt_operation) if interrupt_operation else None,
            'interrupt_receipt': dict(interrupt_receipt) if interrupt_receipt else None,
            'native_requests': native, 'native_pending_count': sum(row['state']=='PENDING' for row in native),
            'core_operations': core_operations, 'active_owned_slots': active_slots, 'pages': pages,
            'cursor': stream['cursor'], 'watermark': stream['watermark'], 'collector_request_state_observed_post_exit': state['requests'][RID]['state'],
            'collector_post_exit_sha256': tokens.fingerprint(state), 'collector_summary': summary,
            'usage_components': components, 'cached_input_is_subset_of_input': True, 'reasoning_output_is_subset_of_output': True,
            'carry_in_tokens': 272648, 'request12_observed_tokens': summary['known_observed_tokens'],
            'cumulative_observed_tokens': 272648 + summary['known_observed_tokens'], 'charged_reservations': 12,
            'refunds': 0, 'new_admissions_during_reconciliation': 0, 'request13_selected': False,
            'useful_result_acceptance': False, 'm1_acceptance': False, 'provider_billing_finality_claimed': False,
            'physical_exit': pin(physical_path), 'final_presence': pin(presence_path),
            'interrupt_admission': pin(HERE/'runtime/execute-result.json'), 'source': pin(__file__), 'runtime_freeze': pin(freeze),
            'method': 'mode=ro, query_only; exact session/operation metadata and token counter projection only; no event bodies, transcript, auth or credentials',
            'bounds_seconds': {'snapshot': 1, 'schema_initialization': 2, 'offline_total': 30},
            'live_bounds_unchanged': True, 'observed_at': time.time(), 'elapsed_seconds': time.monotonic()-started}
        write(HERE/'accounting-reconciliation.json', evidence)
        print(json.dumps({k:evidence[k] for k in ('cumulative_observed_tokens','charged_reservations','request12_observed_tokens','usage_components','cursor','watermark')}))
    finally:
        reader.close()
        journal.close()

if __name__ == '__main__': main()
