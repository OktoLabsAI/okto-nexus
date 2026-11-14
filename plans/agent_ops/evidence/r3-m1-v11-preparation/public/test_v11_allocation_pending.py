"""Actual rebased controller/collector: five reservations, sixth denied, reload retains budget."""
from copy import deepcopy
import json
import pytest
import token_collector as tokens
from controller import POLICY, ANCESTRY, Refused
from test_independent import deny_external, create_control, attach, consume, CanonicalFixture, JournalFixture

def test_actual_five_requests_roundtrip_sixth_refused(tmp_path):
    assert POLICY=={'revision':11,'carry_in_admissions':6,'carry_in_tokens':89473,
        'max_cumulative_admissions':11,'max_new_admissions':5,'preventive_cumulative_tokens':200000,
        'operational_tolerance':700000,'deadline_seconds':120}
    assert ANCESTRY['closure_sha256']=='c3d3e5f5b5b8fbec2c86ea711350ba1a7de44022e568b1c6cfc4fe2e93ff6db0'
    home=tmp_path/'nexus-home';home.mkdir();fixture=CanonicalFixture(home)
    control=create_control(tmp_path);flow,reader,stops=attach(control,fixture,tmp_path,home);writer=None
    try:
        for index in range(5):
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
            assert summary['reserved_requests']==6+index+1
            assert summary['known_observed_tokens']==89473+(index+1)*10
        assert len([call for call in flow.calls if call[0]=='POST'])==5
        assert summary['can_admit'] is False and 'GLOBAL_ALLOCATION_EXHAUSTED' in summary['reasons']
        restored=tokens.restore(tokens.checkpoint(control.accounting))
        assert restored==control.accounting and restored['max_requests']==5
        stream=next(iter(restored['streams']))
        denied,allowed=tokens.reserve(restored,request_id='sixth',stream=stream,stage='continuation')
        assert not allowed and len(denied['requests'])==5
        control.close();control=create_control(tmp_path,create=False)
        flow,reader,stops=attach(control,fixture,tmp_path,home)
        assert control.summary()['reserved_requests']==11
        with pytest.raises(Refused,match='NEW_DISPATCH_NOT_PERMITTED'):
            control.start_work('sixth','local','synthetic',binding=flow.selected,
                checkpoint={'session_id':flow.selected['session_id']},stage='continuation')
        assert not flow.calls and len(control.data['requests'])==5
    finally:
        control.close()
        if writer:writer.close()

def test_collector_rejects_previous_six_request_policy_even_with_valid_hash():
    state=tokens.initial_state();assert state['max_requests']==5
    state['max_requests']=6
    with pytest.raises(tokens.Invalid,match='CHECKPOINT_INVALID'):
        tokens.restore(tokens.checkpoint(state))

def test_actual_legacy_state_rejects_six_records_even_with_valid_seal(tmp_path):
    from legacy_controller import seal
    control=create_control(tmp_path)
    try:
        control.data['requests']={str(i):{'kind':'setup','settled':True,'monitor':{'high_water':0}} for i in range(6)}
        control.data['state_sha256']=seal(control.data)
        with pytest.raises(Refused,match='CONTROLLER_STATE_INVALID'):control._validate()
    finally:control.close()
