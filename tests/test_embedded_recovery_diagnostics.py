"""Real local SQLite failures retain classification, never arbitrary text."""
import json
import sqlite3

import pytest

from nexus_connector_core import CoreError
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.diagnostics import safe_db_diagnostic
from okto_nexus.adapters.outbound.sqlite.write_gate import WriterAdmissionTimeout
from okto_nexus.bootstrap.embedded_agent_recovery import _diagnostic
from okto_nexus.config import NexusConfig
from okto_nexus.errors import ErrorCode, OktoNexusError, db_error_from_exception


def factory_at(tmp_path):
    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path, busy_timeout_ms=10))
    with factory.unit_of_work() as uow:
        uow.connection.execute('CREATE TABLE samples(value TEXT UNIQUE)')
    return factory


def metadata(error):
    text = _diagnostic(error)
    return text, json.loads(text[text.index('{'):])


def test_real_sqlite_writer_lock_preserves_driver_code_and_retryability(tmp_path):
    factory = factory_at(tmp_path)
    holder = factory.get_connection()
    holder.execute('BEGIN IMMEDIATE')
    try:
        with pytest.raises(OktoNexusError) as caught:
            with factory.unit_of_work():
                pytest.fail('A competing SQLite writer must not enter')
    finally:
        holder.close()
    error = caught.value
    assert isinstance(error.__cause__, sqlite3.OperationalError)
    text, details = metadata(error)
    assert details == {'retryable': True, 'sqlite_errorcode': sqlite3.SQLITE_BUSY,
                       'sqlite_errorname': 'SQLITE_BUSY',
                       'sqlite_primary_errorcode': sqlite3.SQLITE_BUSY,
                       'sqlite_primary_errorname': 'SQLITE_BUSY'}
    assert 'database is locked' not in text and str(tmp_path) not in text
    with factory.unit_of_work() as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM samples').fetchone()[0] == 0


def test_real_writer_gate_timeout_is_distinct_from_sqlite_busy(tmp_path):
    factory = factory_at(tmp_path)
    with factory.unit_of_work():
        with pytest.raises(OktoNexusError) as caught:
            with factory.unit_of_work():
                pytest.fail('The local gate must expire before SQLite BEGIN')
    assert isinstance(caught.value.__cause__, WriterAdmissionTimeout)
    assert isinstance(caught.value.__cause__, TimeoutError)
    text, details = metadata(caught.value)
    assert details == {'retryable': True, 'writer_gate_timeout': True}
    assert 'SQLite writer admission timed out' not in text
    with factory.unit_of_work():
        pass  # A diagnostic must not retain writer ownership.


def test_extended_constraint_code_survives_explicit_cause_without_sql_or_values(tmp_path):
    connection = sqlite3.connect(tmp_path / 'private-secret-path.sqlite')
    try:
        connection.execute('CREATE TABLE private_secret_column(value TEXT UNIQUE)')
        connection.execute('INSERT INTO private_secret_column VALUES(?)', ('sensitive-private-value',))
        try:
            connection.execute('INSERT INTO private_secret_column VALUES(?)', ('sensitive-private-value',))
        except sqlite3.IntegrityError as original:
            wrapped = db_error_from_exception('sensitive SQL INSERT path password', original)
            wrapped.__cause__ = original
        else:
            pytest.fail('Expected an actual SQLite UNIQUE constraint error')
    finally:
        connection.close()
    text, details = metadata(wrapped)
    assert details == {'retryable': False, 'sqlite_errorcode': sqlite3.SQLITE_CONSTRAINT_UNIQUE,
                       'sqlite_errorname': 'SQLITE_CONSTRAINT_UNIQUE',
                       'sqlite_primary_errorcode': sqlite3.SQLITE_CONSTRAINT,
                       'sqlite_primary_errorname': 'SQLITE_CONSTRAINT'}
    for secret in ('private_secret_column', 'sensitive-private-value', 'private-secret-path', 'password', 'INSERT'):
        assert secret not in text


def test_implicit_context_and_cycle_are_bounded_without_copying_messages():
    try:
        raise sqlite3.OperationalError('password=hunter2 path=C:/personal SQL=SELECT secret')
    except sqlite3.OperationalError:
        try:
            raise OktoNexusError(ErrorCode.DB_ERROR, 'Bearer private material', {}, retryable=False)
        except OktoNexusError as caught:
            error = caught
    # A manually constructed driver error has no SQLite result code. No guess.
    assert safe_db_diagnostic(error) == {'retryable': False}
    error.__context__.__context__ = error
    assert safe_db_diagnostic(error) == {'retryable': False}
    text = _diagnostic(error)
    assert not any(secret in text for secret in ('hunter2', 'personal', 'SELECT', 'Bearer'))


def test_suppressed_unrelated_context_is_not_reported():
    hidden = WriterAdmissionTimeout('private context')
    current = ValueError('not the original failure')
    current.__context__ = hidden
    current.__suppress_context__ = True
    assert safe_db_diagnostic(current) == {}


def test_fake_attributes_and_timeout_message_cannot_fabricate_sqlite_or_gate_origin():
    error = TimeoutError('SQLite writer admission timed out.')
    error.sqlite_errorcode = sqlite3.SQLITE_BUSY
    error.sqlite_errorname = 'SQLITE_BUSY'
    error.retryable = 'true'
    assert safe_db_diagnostic(error) == {}
    wrapped = OktoNexusError(ErrorCode.DB_ERROR, 'historical failure without retained cause', {}, retryable=True)
    wrapped.__cause__ = error
    assert safe_db_diagnostic(wrapped) == {'retryable': True}
    assert 'writer_gate_timeout' not in _diagnostic(wrapped)


@pytest.mark.parametrize('name', ['SQLITE_BUSY_BEARER_PRIVATE', 'private password/path', 'SQLITE_CONSTRAINT'])
def test_driver_name_must_match_public_sqlite_constant(name):
    error = sqlite3.OperationalError('private message')
    error.sqlite_errorcode = sqlite3.SQLITE_BUSY
    error.sqlite_errorname = name
    details = safe_db_diagnostic(error)
    assert details['sqlite_errorcode'] == sqlite3.SQLITE_BUSY
    assert 'sqlite_errorname' not in details
    assert name not in json.dumps(details)


def test_existing_technical_core_diagnostic_is_preserved():
    error = CoreError('RECONCILIATION_REQUIRED', 'embedded_session_recovery')
    assert _diagnostic(error) == 'CoreError: RECONCILIATION_REQUIRED at embedded_session_recovery'
    error.details = {'reason': 'safe_technical_reason'}
    assert _diagnostic(error).endswith('(safe_technical_reason)')
    error.details = {'reason': 'C:/private command --password=secret'}
    assert _diagnostic(error) == 'CoreError: RECONCILIATION_REQUIRED at embedded_session_recovery'
