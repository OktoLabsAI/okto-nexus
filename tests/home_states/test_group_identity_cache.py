"""Identity reuse must not retain authority, stale metadata or mutable keys."""
from dataclasses import asdict, replace

import pytest

from okto_nexus.domain import home_entries as domain
from okto_nexus.domain.attention import digest
from okto_nexus.domain.home_entry_pages import revision


def entry():
    connection = domain.ConnectionContext('server', 'executor', 'workspace', 'binding', 'wxb', 'agent')
    return domain.EntryRecord('entry', 'work', {'type': 'direct_operation', 'id': 'op', 'revision': 1},
        'workspace', 'agent', 'Work', 'native_accepted', 'confirmed', None, connection=connection)


def test_repeated_identity_does_not_rehash_or_leak_into_dataclass_payload(monkeypatch):
    record = entry()
    before = asdict(record)
    expected = 'home_group_' + digest(record.group_key())
    calls = []
    original = domain.digest
    monkeypatch.setattr(domain, 'digest', lambda value: (calls.append(value), original(value))[1])
    assert [record.group_id for _ in range(100)] == [expected] * 100
    assert len(calls) == 1
    assert asdict(record) == before


@pytest.mark.parametrize('field', ['server_id', 'executor_id', 'binding_id', 'workspace_id',
                                  'workspace_binding_id', 'agent_id'])
def test_every_connection_identity_change_invalidates_the_cached_hash(field):
    record = entry()
    old = record.group_id
    record.connection = replace(record.connection, **{field: 'different-' + field})
    assert record.group_id == 'home_group_' + digest(record.group_key())
    assert record.group_id != old


def test_metadata_and_status_revision_stay_fresh_while_identity_remains_stable():
    record = entry()
    relations = domain.EntryRelations([record], [], {'work': 'ready'}, connections=(record.connection,))
    before = revision(relations, lambda: None)
    identity = record.group_id
    assert revision(relations, lambda: None) == before
    record.display_state = 'outcome_unknown'
    record.connection = replace(record.connection, host_label='Changed host label')
    relations.connections = (record.connection,)
    assert record.group_id == identity
    assert revision(relations, lambda: None) != before


def test_unlinked_origin_identity_changes_with_its_exact_record_id():
    record = entry()
    record.connection = None
    old = record.group_id
    record.id = 'other-origin'
    assert record.group_id != old
    assert record.group_id == 'home_group_' + digest(record.group_key())


def test_mutable_legacy_keys_never_receive_an_identity_cache():
    record = entry()
    mutable = ['legacy']
    record.group_key = lambda: (1, 'origin', mutable)
    old = record.group_id
    mutable.append('changed')
    assert record.group_id != old
    assert record.group_id == 'home_group_' + digest(record.group_key())
    assert not hasattr(record, '_group_identity_cache')


def test_boolean_and_integer_legacy_values_do_not_alias():
    record = entry()
    record.connection = replace(record.connection, agent_id=1)
    numeric = record.group_id
    record.connection = replace(record.connection, agent_id=True)
    assert record.group_id != numeric
    assert record.group_id == 'home_group_' + digest(record.group_key())


def test_opaque_unicode_identities_keep_the_original_digest():
    record = entry()
    record.connection = replace(record.connection, workspace_id='プロジェクト/😀', agent_id='a"\\é')
    assert record.group_id == 'home_group_' + digest(record.group_key())
