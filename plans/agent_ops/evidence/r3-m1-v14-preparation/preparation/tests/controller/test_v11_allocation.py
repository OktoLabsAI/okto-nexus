"""Actual rebased controller/collector: four reservations, fifth denied, reload retains budget."""
from copy import deepcopy
import json
import pytest
import token_collector as tokens
from controller import POLICY, ANCESTRY, Refused
from test_independent import deny_external, create_control, attach, consume, CanonicalFixture, JournalFixture

def test_actual_four_requests_roundtrip_fifth_refused(tmp_path):
    assert POLICY=={'revision':14,'carry_in_admissions':9,'carry_in_tokens':134199,
        'max_cumulative_admissions':13,'max_new_admissions':4,'preventive_cumulative_tokens':500000,
        'operational_tolerance':700000,'deadline_seconds':600}
    assert ANCESTRY['closure_sha256']=='1170704cfe50b1d96e11bb560f042473dd12d7c827c51f0ae447078d3ba35171'
    home=tmp_path/'nexus-home';home.mkdir();fixture=CanonicalFixture(home)
    # This case isolates reservation policy, not wall-clock performance. The
    # actual modules, SQLite journals, persistence, reopen and API fence remain.
    # Real-clock nominal tests and the preserved 105ms timing failure are separate.
    now=[1000.]
    control=create_control(tmp_path,lambda:now[0]);flow,reader,stops=attach(control,fixture,tmp_path,home);writer=None
    control._readers['local'].io.clock=lambda:now[0]
    reader.io.clock=lambda:now[0]
    try:
        for index in range(4):
            name='allocation-'+str(index)
            checkpoint={} if index==0 else {'session_id':flow.selected['session_id']}
            control.start_work(name,'local','synthetic',binding=flow.selected,checkpoint=checkpoint,
                stage='useful_work' if index==0 else 'continuation')
            result=consume(control);assert result['ok']
            if writer is None:writer=JournalFixture(reader.path(flow.selected),flow.selected)
            writer.complete(name,(index+1)*10);fixture.terminal(name,flow.selected)
            summary=control.poll()
            assert control.data['requests'][name]['settled']
            assert summary['new_reserved_requests']==index+1
            assert summary['reserved_requests']==9+index+1
            assert summary['known_observed_tokens']==134199+(index+1)*10
        assert len([call for call in flow.calls if call[0]=='POST'])==4
        assert summary['can_admit'] is False and 'GLOBAL_ALLOCATION_EXHAUSTED' in summary['reasons']
        restored=tokens.restore(tokens.checkpoint(control.accounting))
        assert restored==control.accounting and restored['max_requests']==4
        stream=next(iter(restored['streams']))
        denied,allowed=tokens.reserve(restored,request_id='fifth',stream=stream,stage='continuation')
        assert not allowed and len(denied['requests'])==4
        control.close();control=create_control(tmp_path,lambda:now[0],create=False)
        flow,reader,stops=attach(control,fixture,tmp_path,home)
        control._readers['local'].io.clock=lambda:now[0]
        reader.io.clock=lambda:now[0]
        assert control.summary()['reserved_requests']==13
        with pytest.raises(Refused,match='NEW_DISPATCH_NOT_PERMITTED'):
            control.start_work('fifth','local','synthetic',binding=flow.selected,
                checkpoint={'session_id':flow.selected['session_id']},stage='continuation')
        assert not flow.calls and len(control.data['requests'])==4
    finally:
        control.close()
        if writer:writer.close()

def test_collector_rejects_previous_five_request_policy_even_with_valid_hash():
    state=tokens.initial_state();assert state['max_requests']==4
    state['max_requests']=5
    with pytest.raises(tokens.Invalid,match='CHECKPOINT_INVALID'):
        tokens.restore(tokens.checkpoint(state))

def test_actual_legacy_state_rejects_five_records_even_with_valid_seal(tmp_path):
    from legacy_controller import seal
    control=create_control(tmp_path)
    try:
        control.data['requests']={str(i):{'kind':'setup','settled':True,'monitor':{'high_water':0}} for i in range(5)}
        control.data['state_sha256']=seal(control.data)
        with pytest.raises(Refused,match='CONTROLLER_STATE_INVALID'):control._validate()
    finally:control.close()
