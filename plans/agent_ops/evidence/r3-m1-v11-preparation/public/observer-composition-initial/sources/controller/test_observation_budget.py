"""Deterministic clock checks, offline fixtures only."""
import sqlite3
import pytest
from test_independent import deny_external,create_control,CanonicalFixture,JournalFixture,attach,consume
from test_cached_readonly import fixture_db
from independent_journal import ReadOnly,JournalUnknown
from independent_controller import PollBudgetExceeded
from api_worker import EffectFence,SerialAPI,Fenced
from legacy_controller import Controller as LegacyController,POLICY


class SlowRollback:
    def __init__(self,db,clock,*,fail=False):self.db=db;self.clock=clock;self.fail=fail
    def __getattr__(self,name):return getattr(self.db,name)
    def rollback(self):
        self.clock[0]+=.101
        if self.fail:raise sqlite3.OperationalError('synthetic rollback failure')
        return self.db.rollback()


def test_snapshot_clock_includes_rollback_and_closes_on_exhaustion(tmp_path):
    now=[0.];io=ReadOnly(tmp_path,clock=lambda:now[0]);path=fixture_db(tmp_path)
    entry=io.prepare(path);entry['db']=SlowRollback(entry['db'],now)
    with pytest.raises(JournalUnknown,match='READ_BUDGET_EXCEEDED'):
        with io.open(path) as db:assert db.execute('SELECT value FROM observation').fetchone()[0]==1
    assert io.failed and not io.connections


def test_aggregate_primary_survives_failed_rollback_but_cache_is_discarded(tmp_path):
    now=[0.];io=ReadOnly(tmp_path,clock=lambda:now[0]);path=fixture_db(tmp_path)
    entry=io.prepare(path);raw=entry['db'];entry['db']=SlowRollback(raw,now,fail=True)
    primary=PollBudgetExceeded('OBSERVATION_POLL_BUDGET_EXCEEDED')
    with pytest.raises(PollBudgetExceeded) as caught:
        with io.open(path):raise primary
    assert caught.value is primary and io.failed and not io.connections
    assert io.close_error_types
    with pytest.raises(sqlite3.ProgrammingError):raw.execute('SELECT 1')


def test_aggregate_only_preserves_reader_for_late_observations(tmp_path):
    now=[0.];io=ReadOnly(tmp_path,clock=lambda:now[0]);path=fixture_db(tmp_path);entry=io.prepare(path)
    primary=PollBudgetExceeded('OBSERVATION_POLL_BUDGET_EXCEEDED')
    with pytest.raises(PollBudgetExceeded):
        with io.open(path):raise primary
    assert not io.failed and entry['db'].in_transaction is False
    with io.open(path) as db:assert db.execute('SELECT value FROM observation').fetchone()[0]==1
    io.close()


def test_public_observation_includes_io_before_snapshot(tmp_path):
    now=[0.];io=ReadOnly(tmp_path,clock=lambda:now[0])
    def path_checks():now[0]=.101;return None
    with pytest.raises(JournalUnknown,match='READ_BUDGET_EXCEEDED'):io.observe(path_checks)
    assert io.failed


@pytest.mark.parametrize('mode',['freshness','poll_budget'])
def test_worker_post_checks_new_clock_after_get_io(mode):
    now=[0.];fence=EffectFence(lambda:now[0]);fence.observation_required=True
    fence.end_poll(0,True)
    if mode=='poll_budget':fence.begin_poll(0,.6)
    api=SerialAPI(fence);calls=[]
    def raw(method,path,body=None):calls.append(method);now[0]=1.001 if mode=='freshness' else .601
    call=api.transport(raw)
    def job():call('GET','synthetic');call('POST','synthetic')
    api.submit('one',job,productive=True);assert api.done.wait(2)
    result=api.take()
    assert not result['ok'] and isinstance(result['error'],Fenced)
    assert calls==['GET'] and fence.event.is_set()
    assert fence.reason==('OBSERVATION_STALE' if mode=='freshness' else 'OBSERVATION_POLL_BUDGET_EXCEEDED')


def test_first_setup_gets_complete_fresh_empty_poll_before_effect(tmp_path):
    now=[1000.];home=tmp_path/'home';home.mkdir();control=create_control(tmp_path,lambda:now[0]);effects=[]
    try:
        control.setup('first','local',home,lambda:effects.append('dispatch'),lambda:None)
        assert effects==['dispatch'] and control.fence.fresh_until==1001
        assert control.fence.poll_deadline is None
    finally:control.close()


def test_poll_checks_new_clock_after_final_persist_and_does_not_refresh(tmp_path,monkeypatch):
    now=[1000.];control=create_control(tmp_path,lambda:now[0]);original=control.persist;delay=[True]
    def slow(accounting=None):
        value=original(accounting)
        if delay[0]:delay[0]=False;now[0]+=.601
        return value
    monkeypatch.setattr(control,'persist',slow)
    try:
        summary=control.poll()
        assert 'OBSERVATION_POLL_BUDGET_EXCEEDED' in summary['reasons']
        assert control.fence.event.is_set() and control.fence.fresh_until is None
    finally:control.close()


def test_deadline_crossed_during_final_persist_is_faulted_before_return(tmp_path,monkeypatch):
    now=[1000.];home=tmp_path/'home';home.mkdir();control=create_control(tmp_path,lambda:now[0]);stops=[]
    try:
        control.setup('first','local',home,lambda:None,lambda:stops.append('stop'))
        now[0]=1119.9;control._last_poll=1119.8
        original=control.persist;delay=[True]
        def slow(accounting=None):
            value=original(accounting)
            if delay[0]:delay[0]=False;now[0]+=.2
            return value
        monkeypatch.setattr(control,'persist',slow)
        summary=control.poll()
        assert 'DEADLINE120' in summary['reasons'] and stops==['stop']
        assert 'OBSERVATION_POLL_BUDGET_EXCEEDED' not in summary['reasons']
        assert control.fence.event.is_set() and control.fence.fresh_until==1001
    finally:control.close()


def test_usage_fences_effects_before_durable_io(tmp_path,monkeypatch):
    now=[1000.];home=tmp_path/'home';home.mkdir();fixture=CanonicalFixture(home)
    control=create_control(tmp_path,lambda:now[0]);flow,reader,stops=attach(control,fixture,tmp_path,home)
    writer=None;checked=[]
    try:
        control.start_work('one','local','synthetic',binding=flow.selected,checkpoint={});consume(control)
        writer=JournalFixture(reader.path(flow.selected),flow.selected)
        writer.complete('one',POLICY['preventive_cumulative_tokens']-POLICY['carry_in_tokens'])
        fixture.terminal('one',flow.selected)
        original=LegacyController.persist
        def blocked_io(self,accounting=None):
            if accounting is not None:
                assert self.fence.known_tokens>=POLICY['preventive_cumulative_tokens']
                with pytest.raises(Fenced):self.fence.require('POST')
                checked.append(True)
            return original(self,accounting)
        monkeypatch.setattr(LegacyController,'persist',blocked_io)
        control.poll()
        assert checked and stops==['normal-stop']
    finally:
        control.close()
        if writer:writer.close()
