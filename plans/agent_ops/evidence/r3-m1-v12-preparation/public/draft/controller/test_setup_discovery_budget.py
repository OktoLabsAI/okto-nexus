"""Deterministic discovery vs SQL budgets; only synthetic own fixtures."""
from pathlib import Path
import sqlite3
import pytest
import setup_journal as setup
from independent_journal import ReadOnly,JournalUnknown
from independent_controller import PollBudgetExceeded
from test_independent import deny_external,create_control


def armed(tmp_path):
    home=tmp_path/'home';home.mkdir()
    return setup.arm(home,tmp_path)


@pytest.mark.parametrize('duration',[.317,.599])
def test_absent_journal_discovery_uses_aggregate_not_sql_limit(tmp_path,monkeypatch,duration):
    record=armed(tmp_path);now=[0.];io=ReadOnly(tmp_path,clock=lambda:now[0]);real=setup.safe_path
    def slow(path,owner):
        result=real(path,owner);now[0]+=duration;return result
    monkeypatch.setattr(setup,'safe_path',slow)
    def aggregate():
        if now[0]>=.6:raise PollBudgetExceeded('OBSERVATION_POLL_BUDGET_EXCEEDED')
    io.aggregate_check=aggregate
    try:
        result=setup.poll(record,io=io)
        assert result['journal'] is None and not result['started'] and not result['usage_seen']
        assert not io.failed and not io.connections and not io.initializations
    finally:io.close()


def test_absent_journal_over600ms_keeps_aggregate_failure(tmp_path,monkeypatch):
    record=armed(tmp_path);now=[0.];io=ReadOnly(tmp_path,clock=lambda:now[0]);real=setup.safe_path
    def slow(path,owner):
        result=real(path,owner);now[0]+=.601;return result
    monkeypatch.setattr(setup,'safe_path',slow)
    primary=PollBudgetExceeded('OBSERVATION_POLL_BUDGET_EXCEEDED')
    def aggregate():
        if now[0]>=.6:raise primary
    io.aggregate_check=aggregate
    try:
        with pytest.raises(PollBudgetExceeded) as caught:setup.poll(record,io=io)
        assert caught.value is primary and not io.connections and not io.initializations
    finally:io.close()


def journal_path(record):
    path=Path(record['root'])/('a'*32)/'journal.db';path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:db.execute('CREATE TABLE synthetic(value INTEGER)')
    return path


def test_setup_snapshot_still_refuses251ms_and_closes(tmp_path,monkeypatch):
    record=armed(tmp_path);path=journal_path(record);now=[0.];io=ReadOnly(tmp_path,clock=lambda:now[0])
    entry=io.prepare(path);raw=entry['db']
    class SlowRead:
        def __getattr__(self,name):return getattr(raw,name)
        def execute(self,query,*args):
            result=raw.execute(query,*args)
            if query.startswith('SELECT name FROM sqlite_master'):now[0]+=.251
            return result
    entry['db']=SlowRead()
    try:
        with pytest.raises(JournalUnknown,match='READ_BUDGET_EXCEEDED'):setup.poll(record,io=io)
        assert io.failed and not io.connections
    finally:io.close()


def test_setup_schema_still_refuses251ms_and_closes(tmp_path):
    record=armed(tmp_path);journal_path(record);now=[0.]
    def clock():now[0]+=.251;return now[0]
    io=ReadOnly(tmp_path,clock=clock)
    try:
        with pytest.raises(JournalUnknown,match='INITIALIZATION_BUDGET_EXCEEDED'):setup.poll(record,io=io)
        assert io.failed and io.initializations[0]['budget_ms']==250 and not io.connections
    finally:io.close()


def test_absent_journal_does_not_hide_owner_replacement(tmp_path):
    record=armed(tmp_path);record['home_identity'][1]+=1;io=ReadOnly(tmp_path)
    try:
        with pytest.raises(setup.SetupUnknown,match='OWNER_CHANGED'):setup.poll(record,io=io)
        assert not io.initializations
    finally:io.close()


@pytest.mark.parametrize('method',['is_junction','is_symlink'])
def test_absent_journal_does_not_hide_reparse(tmp_path,monkeypatch,method):
    record=armed(tmp_path);target=Path(record['root']);real=getattr(Path,method)
    monkeypatch.setattr(Path,method,lambda self:True if self==target else real(self))
    io=ReadOnly(tmp_path)
    try:
        with pytest.raises(setup.SetupUnknown,match='SETUP_PATH_LINK'):setup.poll(record,io=io)
    finally:io.close()


@pytest.mark.parametrize('duration,failed',[(.317,False),(.601,True)])
def test_controller_retains_freshness_and_aggregate_fence(tmp_path,monkeypatch,duration,failed):
    now=[1000.];home=tmp_path/'home';home.mkdir();control=create_control(tmp_path,lambda:now[0]);stops=[]
    try:
        control.setup('first','local',home,lambda:None,lambda:stops.append('stop'))
        real=setup.safe_path
        def slow(path,owner):
            value=real(path,owner);now[0]+=duration;return value
        monkeypatch.setattr(setup,'safe_path',slow)
        result=control.poll()
        assert ('OBSERVATION_POLL_BUDGET_EXCEEDED' in result['reasons']) is failed
        assert ('OBSERVATION_UNKNOWN' in result['reasons']) is False
        assert control.fence.event.is_set() is failed
        assert stops==(['stop'] if failed else [])
        assert control.data['requests']['first']['monitor']['journal'] is None
        assert result['new_reserved_requests']==1 and result['new_observed_tokens']==0
        assert control.fence.fresh_until==1001
    finally:control.close()
