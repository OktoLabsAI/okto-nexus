"""Cache/snapshot guards with real SQLite; no services, provider or credentials."""
from pathlib import Path
import hashlib,json,sqlite3,threading,time
import pytest
from independent_journal import ReadOnly,CanonicalIntentReader,CoreJournalReader,JournalUnknown
from test_independent import deny_external,CanonicalFixture,JournalFixture,scope,create_control,attach,consume
import token_collector as tokens


def fixture_db(root):
    path=root/'fixture.db'
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE observation(value INTEGER)');db.execute('INSERT INTO observation VALUES(1)')
    return path


def test_real_closed_v10_full_schema_prepares_once_and_stays_readonly(tmp_path):
    campaign=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v10-bundle-pscf18t5/campaign')
    path=campaign/'nexus-home/nexus.db';before=hashlib.sha256(path.read_bytes()).hexdigest()
    io=ReadOnly(campaign);durations=[];connection_ids=[]
    try:
        io.prepare(path)
        for _ in range(8):
            started=time.monotonic()
            with io.open(path) as db:
                connection_ids.append(id(db))
                assert db.execute('PRAGMA query_only').fetchone()[0]==1
                assert db.execute('SELECT count(*) FROM execution_client_intents').fetchone()[0]==0
            assert not db.in_transaction
            durations.append((time.monotonic()-started)*1000)
        assert len(set(connection_ids))==1 and len(io.initializations)==1
        assert io.initializations[0]['budget_ms']==250
        assert io.initializations[0]['elapsed_ms']<250
        assert len(io.connections)==1
        evidence={'source_db_sha256':before,'schema_preparation':io.diagnostics(),
                  'warm_read_ms':durations,'same_connection':True,'fresh_transaction_each_read':True}
        (tmp_path/'real-reader-evidence.json').write_text(json.dumps(evidence,indent=2))
    finally:io.close()
    assert before==hashlib.sha256(path.read_bytes()).hexdigest()
    assert io.diagnostics()['open_connections']==0


def test_fresh_wal_snapshot_and_no_read_lock_between_polls(tmp_path):
    path=fixture_db(tmp_path);io=ReadOnly(tmp_path)
    try:
        with io.open(path) as db:assert db.execute('SELECT value FROM observation').fetchone()[0]==1
        assert not db.in_transaction
        with sqlite3.connect(path,timeout=.04) as writer:
            writer.execute('UPDATE observation SET value=2')
        with io.open(path) as same:
            assert same is db and same.execute('SELECT value FROM observation').fetchone()[0]==2
        assert not same.in_transaction
        with sqlite3.connect(path) as writer:
            assert writer.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0]==0
    finally:io.close()


def test_none_and_error_paths_always_release_transaction(tmp_path):
    path=fixture_db(tmp_path);io=ReadOnly(tmp_path)
    def no_value():
        with io.open(path) as db:
            assert db.execute('SELECT value FROM observation WHERE value=99').fetchone() is None
            return None
    assert no_value() is None
    db=next(iter(io.connections.values()))['db'];assert not db.in_transaction
    primary=ValueError('synthetic primary')
    with pytest.raises(ValueError) as caught:
        with io.open(path) as db:raise primary
    assert caught.value is primary and io.failed and not io.connections
    with pytest.raises(sqlite3.ProgrammingError):db.execute('SELECT 1')
    io.close()


def test_unrelated_schema_evolution_is_observed_with_same_connection(tmp_path):
    path=fixture_db(tmp_path);io=ReadOnly(tmp_path)
    cached=io.prepare(path)['db']
    with sqlite3.connect(path) as writer:writer.execute('CREATE TABLE changed_schema(x INTEGER)')
    with io.open(path) as db:
        assert db is cached and db.execute('SELECT value FROM observation').fetchone()[0]==1
    assert len(io.initializations)==1 and not io.failed
    assert len(io.schema_changes)==1
    io.close()


def test_file_identity_drift_is_refused_and_cache_closed(tmp_path):
    path=fixture_db(tmp_path);io=ReadOnly(tmp_path);io.prepare(path)
    identity=io.identities[str(path)];io.identities[str(path)]=(identity[0],identity[1]+1)
    with pytest.raises(JournalUnknown,match='DATABASE_REPLACED'):
        with io.open(path):pass
    assert io.failed and not io.connections
    io.close()


def test_path_junction_revalidation_fails_closed(tmp_path,monkeypatch):
    path=fixture_db(tmp_path);io=ReadOnly(tmp_path);io.prepare(path)
    original=Path.is_junction
    monkeypatch.setattr(Path,'is_junction',lambda self:True if self==path else original(self))
    with pytest.raises(JournalUnknown,match='PATH_LINK'):
        with io.open(path):pass
    assert io.failed and not io.connections
    io.close()


def test_warmed_query_still_interrupts_at40ms_and_never_retries(tmp_path):
    path=fixture_db(tmp_path);clock=[0.];io=ReadOnly(tmp_path,sql_budget=.04,clock=lambda:clock[0]);io.prepare(path)
    with pytest.raises(sqlite3.OperationalError) as caught:
        with io.open(path) as db:
            clock[0]=.041
            db.execute('WITH RECURSIVE numbers(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM numbers WHERE x<10000) SELECT sum(x) FROM numbers').fetchone()
    assert caught.value.sqlite_errorcode==sqlite3.SQLITE_INTERRUPT
    assert io.failed and not io.connections
    with pytest.raises(JournalUnknown,match='READER_FAILED'):io.prepare(path)
    assert len(io.initializations)==1
    io.close()


def test_initialization_budget_is_separate_explicit_and_fails_closed(tmp_path):
    path=fixture_db(tmp_path);ticks=[0.]
    def clock():ticks[0]+=.26;return ticks[0]
    io=ReadOnly(tmp_path,clock=clock)
    with pytest.raises(JournalUnknown,match='INITIALIZATION_BUDGET_EXCEEDED'):io.prepare(path)
    assert io.failed and not io.connections
    assert io.diagnostics()['initializations'][0]['budget_ms']==250
    assert io.diagnostics()['initializations'][0]['status']=='FAILED'
    io.close()


def test_closed_or_other_owner_cannot_reuse_connections(tmp_path):
    path=fixture_db(tmp_path);io=ReadOnly(tmp_path);io.prepare(path);errors=[]
    def wrong():
        try:io.prepare(path)
        except JournalUnknown as error:errors.append(str(error))
    thread=threading.Thread(target=wrong);thread.start();thread.join()
    assert errors==['READER_OWNER_CHANGED']
    io.close();io.close()
    with pytest.raises(JournalUnknown,match='READER_CLOSED'):io.prepare(path)


def test_core_journal_can_initialize_after_reservation_and_controller_closes_all(tmp_path):
    home=tmp_path/'nexus-home';home.mkdir();fixture=CanonicalFixture(home);control=create_control(tmp_path)
    flow,reader,stops=attach(control,fixture,tmp_path,home);writer=None
    canonical=control._readers['local']
    assert len(canonical.io.connections)==1 and not reader.io.connections
    try:
        control.start_work('one','local','synthetic',binding=flow.selected,checkpoint={});consume(control)
        assert not reader.io.connections
        writer=JournalFixture(reader.path(flow.selected),flow.selected)
        writer.complete('one',10);fixture.terminal('one',flow.selected)
        control.poll()
        assert len(reader.io.initializations)==1 and len(reader.io.connections)==1
        assert control.data['requests']['one']['settled']
    finally:
        control.close()
        if writer:writer.close()
    assert canonical.io.closed and reader.io.closed
    assert not canonical.io.connections and not reader.io.connections


def test_core_partial_schema_then_legitimate_ddl_and_required_schema_drop(tmp_path):
    owner=tmp_path/'owner';owner.mkdir();selected=scope()
    reader=CoreJournalReader(tmp_path,owner,'local');path=reader.path(selected)
    path.parent.mkdir();sqlite3.connect(path).close()
    assert reader.read(selected) is None
    cached=reader.io.connections[str(path)]['db'];writer=JournalFixture(path,selected)
    try:
        writer.complete('one',10)
        page=reader.read(selected);assert page['count']==3
        assert reader.io.connections[str(path)]['db'] is cached
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE process_containers(server_id TEXT,executor_id TEXT,session_id TEXT,container_id TEXT,PRIMARY KEY(server_id,executor_id,session_id))')
        assert reader.read(selected,3)['count']==0
        assert len(reader.io.schema_changes)==2
        with sqlite3.connect(path) as db:db.execute('DROP TABLE events')
        with pytest.raises(JournalUnknown,match='JOURNAL_SCHEMA_ROLLBACK'):reader.read(selected,3)
        assert reader.io.failed
    finally:reader.close();writer.close()
