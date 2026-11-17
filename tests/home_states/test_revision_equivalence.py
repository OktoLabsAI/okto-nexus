"""Revision optimization against the previous algorithm, not a new wire contract."""
from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from okto_nexus.domain import home_entry_pages, home_harness_board
from okto_nexus.domain.attention import canonical, digest
from okto_nexus.domain.home_entries import (
    ConnectionContext,
    EntryRecord,
    EntryRelations,
    SessionContext,
)
from tests.home_states.test_operational_status import NOW, facts, question


def old_material(relations, check_budget):
    entries = []
    for entry in sorted(relations.entries, key=lambda item: item.id):
        check_budget()
        value = asdict(entry)
        for name, key in (('operations', 'operation_id'), ('attention', 'attention_id'),
                          ('results', 'id'), ('external', 'observed_instance_id')):
            value[name].sort(key=lambda row: (row[key], canonical(row)))
        entries.append(value)
    return {
        'entries': entries,
        'server_attention': sorted(relations.server_attention, key=lambda row: row['attention_id']),
        'source_status': relations.source_status, 'connection_count': relations.connection_count,
        'connections': None if relations.connections is None else sorted(
            (asdict(c) for c in relations.connections), key=canonical),
    }


def old_revision(relations, check_budget):
    result = digest(old_material(relations, check_budget))
    check_budget()
    return result


def sample():
    c = ConnectionContext('server', 'executor', 'ws', 'binding', 'wxb', 'agent',
                          'codex_app_server', 'Project 雪', 'Host', 'Collaborator', 'public-id')
    s = SessionContext('server', 'executor', 'ws', 'session', 'binding', 'wxb', 'agent', 'READY')
    shared = {'id': 'result', 'nested': {'values': [None, True, '雪', {'x': 1.25}]}}
    a = EntryRecord('b', 'work', {'type': 'handoff', 'id': 'h', 'revision': 'r'}, 'ws', 'agent',
        'Work', 'running', 'confirmed', {'kind': 'session', 'session_id': 'session'}, c, (s,),
        operations=[{'operation_id': 'same', 'value': 2}, {'operation_id': 'same', 'value': 1}],
        attention=[{'attention_id': 'z', 'allowed_actions': ['inspect']}, {'attention_id': 'a'}],
        results=[shared, {'id': 'a'}, shared], external=[{'observed_instance_id': 'e', 'generation': 2}],
        activity={'metadata': {'rows': [1, 2]}}, registered_connections=(c, c))
    b = replace(a, id='a', results=[shared], sessions=(s, s))
    a.private_diagnostic = 'not part of dataclass fields'
    return EntryRelations([a, b], [{'attention_id': 'z'}, {'attention_id': 'a'}],
                          {'results': 'ready'}, 2, (replace(c, binding_id='second'), c, c))


@pytest.mark.parametrize('unknown_connections', [False, True])
def test_exact_canonical_bytes_hash_budget_and_no_input_mutation(monkeypatch, unknown_connections):
    rel = sample()
    if unknown_connections:
        rel.connections = rel.connection_count = None
    before = deepcopy(rel)
    old_calls, calls, captured = [], [], []
    material = old_material(rel, lambda: old_calls.append(1))
    old_calls.append(1)

    def capture(value):
        captured.append(canonical(value))
        return digest(value)

    monkeypatch.setattr(home_entry_pages, 'digest', capture)
    assert home_entry_pages.revision(rel, lambda: calls.append(1)) == digest(material)
    assert captured == [canonical(material)]
    assert calls == old_calls and rel == before
    assert rel.entries[0].results[0] is rel.entries[1].results[0]
    assert rel.entries[0].operations[0]['value'] == 2


@pytest.mark.parametrize('change', ['nested', 'context', 'source', 'inventory', 'target'])
def test_aliases_and_mutations_between_calls_never_reuse_snapshot(change):
    rel = sample()
    first = home_entry_pages.revision(rel, lambda: None)
    if change == 'nested':
        rel.entries[0].results[0]['nested']['values'].append('new')
    elif change == 'context':
        rel.entries[0].connection = replace(rel.entries[0].connection, workspace_binding_id='rotated')
    elif change == 'source':
        rel.source_status['results'] = 'partial'
    elif change == 'inventory':
        rel.connections = tuple(reversed(rel.connections)) + (replace(rel.connections[0], agent_id='other'),)
    else:
        rel.entries[0].target['session_id'] = 'other-session'
    current = home_entry_pages.revision(rel, lambda: None)
    assert current != first and current == old_revision(rel, lambda: None)


def test_input_order_and_equal_id_ties_match_previous_contract():
    rel = sample()
    first = home_entry_pages.revision(rel, lambda: None)
    rel.entries.reverse()
    rel.connections = tuple(reversed(rel.connections))
    for entry in rel.entries:
        for name in ('operations', 'attention', 'results', 'external'):
            getattr(entry, name).reverse()
    assert home_entry_pages.revision(rel, lambda: None) == first == old_revision(rel, lambda: None)


@pytest.mark.parametrize('version', [1, 2])
@pytest.mark.parametrize('phase', ['ready', 'question', 'expired'])
def test_board_envelopes_revisions_and_continuations_match_old_algorithm(monkeypatch, version, phase):
    rel, c, session, _ = facts()
    rel.connections += (replace(c, binding_id='second'), replace(c, binding_id='third'))
    if phase == 'question':
        question(rel, c)
    elif phase == 'expired':
        rel.operational_sessions = (replace(session, valid_until=NOW),)
    kwargs = {'scope': home_entry_pages.filters({'quick': 'all'}), 'server_id': 'server',
              'principal': 'human', 'now': NOW, 'presentation_version': version, 'limit': 1}
    actual = home_harness_board.page(rel, **kwargs)
    cursor = actual['columns']['active']['next_cursor']
    assert cursor is not None
    more = home_harness_board.page(rel, **kwargs, partition='column', column='active', cursor=cursor)
    with monkeypatch.context() as patch:
        patch.setattr(home_entry_pages, 'revision', old_revision)
        assert home_harness_board.page(rel, **kwargs) == actual
        assert home_harness_board.page(rel, **kwargs, partition='column', column='active', cursor=cursor) == more
    # Presentation/principal/scope remain bound even though relation hashes agree.
    from okto_nexus.errors import OktoNexusError
    for altered in ({'principal': 'other'}, {'scope': home_entry_pages.filters({'quick': 'all', 'workspace_id': 'other'})}):
        with pytest.raises(OktoNexusError):
            home_harness_board.page(rel, **(kwargs | altered), partition='column', column='active', cursor=cursor)


def test_budget_exception_still_propagates_without_digest_or_mutation():
    rel = sample()
    before = deepcopy(rel)

    def budget():
        raise TimeoutError('read deadline')

    with pytest.raises(TimeoutError, match='read deadline'):
        home_entry_pages.revision(rel, budget)
    assert rel == before
