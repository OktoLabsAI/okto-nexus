"""UI022 canonical SQLite read semantics, not native execution qualification."""
import json
from pathlib import Path
import tempfile

from measure import fixtures, OUT, HomeEntriesService, SqliteHomeEntryRelations


def main():
    report = dict(checks=[],status='pending')
    with fixtures.scenario(Path(tempfile.mkdtemp(prefix='nexus-ui022-semantics-'))) as s:
        with s.factory.unit_of_work() as uow:
            c = uow.connection
            original = c.execute('SELECT * FROM execution_sessions WHERE session_id=?',(s.sessions[0],)).fetchone()
            opening = c.execute('SELECT * FROM execution_operations WHERE operation_id=?',(original['open_operation_id'],)).fetchone()
            turn = c.execute("SELECT * FROM execution_operations WHERE action='turn.submit'").fetchone()
            for sid, lifecycle in [('ui022-running','READY'),('ui022-idle','READY'),('ui022-opening','OPENING')]:
                scope = dict(json.loads(opening['expected_revisions_json']),session_id=sid)
                fixtures._copy(c,'execution_operations',opening,operation_id=sid+'-open',session_id=sid,
                    expected_revisions_json=json.dumps(scope))
                fixtures._copy(c,'execution_sessions',original,session_id=sid,open_operation_id=sid+'-open',
                    lifecycle_state=lifecycle,lease_state='ACTIVE',stream_epoch=sid+'-epoch')
            fixtures._copy(c,'execution_operations',turn,operation_id='ui022-running-turn',session_id='ui022-running',
                expected_revisions_json=json.dumps(dict(json.loads(turn['expected_revisions_json']),
                    session_id='ui022-running',session_owner_generation=original['owner_generation'])))
            key = (turn['server_id'],turn['executor_id'])
            c.execute("INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,stage,possible_effect,retry_safe,received_at) VALUES(?,?,'ui022-running-turn',1,?,'SUBMITTED',1,0,?)",
                (*key,turn['intent_hash'],s.clock.now_iso()))
            c.execute("INSERT INTO execution_event_ingress VALUES(?,?,'ui022-running','ui022-running-epoch',1,'own-synthetic-start','turn_state',?,?)",
                (*key,json.dumps({'operation_id':'ui022-running-turn','payload':{'delivery_phase':'started'}}),s.clock.now_iso()))
            c.execute("INSERT INTO execution_event_watermarks VALUES(?,?,'ui022-running','ui022-running-epoch',1,1,'none')",key)
            c.execute("UPDATE handoffs SET status='CLAIMED',claimed_by='B',claim_epoch=1,lease_expires_at=? WHERE handoff_id='ui-handoff-0'",('2026-11-16T13:00:00.000000Z',))
        service = HomeEntriesService(s.app.state.home,queries=SqliteHomeEntryRelations())
        first = service.read(context=s.operator,filters={'quick':'all'},limit=100,preview=100)
        assert first['status']=='ready',first
        entries = [e for g in first['items'] for e in g['children']]
        bysource = {e['source_ref']['id']:e for e in entries}
        running = bysource['ui022-running-turn']
        waiting = [e for e in entries if e['display_state']=='awaiting_operator']
        assert running['display_state']=='running'
        assert len(waiting)==1 and waiting[0]['target']['session_id']==s.sessions[0]
        assert running['target']['session_id']=='ui022-running'
        assert running['id'] != waiting[0]['id']
        report['checks'].append('same agent: exact second session running; original session awaiting_operator, distinct stable IDs')
        for sid in ('ui022-idle','ui022-opening'):
            e = next(e for e in entries if e['kind']=='session' and e['target']['session_id']==sid)
            assert e['display_state'] != 'running' and 'operation_id' not in e['target']
        report['checks'].append('READY and OPENING without turn stay passive session context, never productive running')
        assert bysource['ui-handoff-0']['display_state']=='claimed'
        assert bysource['ui-unknown']['display_state']=='outcome_unknown'
        assert bysource['ui-success']['display_state']=='result_available_cleanup_pending'
        report['checks'].append('CLAIMED remains claimed; uncertain remains outcome_unknown; SUCCEEDED plus containment remains result_available_cleanup_pending')
        report.update(status='PASS',summary=first['summary'],entries=[dict(id=e['id'],kind=e['kind'],
            state=e['display_state'],source_ref=e['source_ref'],target=e['target']) for e in entries],
            limitation='Synthetic persisted read facts including started ingress; no native binary/provider/dispatch qualification. Warm lease alone not qualified as execution.')
    report['cleanup']='shared own fixture context exited normally; WSS/lifespan/factory closed; no browser or server process created'
    (OUT/'semantics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(status=report['status'],checks=len(report['checks']))))


if __name__=='__main__':
    main()
