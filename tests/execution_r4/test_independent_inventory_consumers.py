"""Partial observations preserve consent without granting stale execution."""
import copy
import json
import time

import pytest
from nexus_connector_core import InstallationCandidate, build_executor_inventory_snapshot
from nexus_connector_core.executor_inventory import _revision

from okto_nexus.application.execution_inventory_freshness import inventory_is_fresh
from okto_nexus.application.execution_inventory_revalidation import accepts_binding, compatible_selection, selection
from okto_nexus.application.executor_inventory import publish_executor_inventory
from okto_nexus.domain.execution.keys import ExecutorKey
from test_binding_operator import onboarding
from test_binding_views import bound, read
from test_local_realization import local_setup
from test_local_launch import admitted_local


def sample():
    candidate = InstallationCandidate('codex_app_server', '/synthetic/codex',
        'sha256:' + 'a' * 64, 'explicit', 'selected')
    return build_executor_inventory_snapshot((candidate,), server_id='server', executor_id='executor',
        producer_instance_id='owner', publication_sequence=1)


def current(snapshot):
    return dict(publication_sequence=snapshot['publication_sequence'],
                canonical_projection=json.dumps(snapshot))


@pytest.mark.parametrize('state', ['old', 'PENDING', 'FAILED', 'ABSENT'])
def test_fresh_sibling_cannot_refresh_selected_harness(state):
    snapshot = sample()
    row = next(item for item in snapshot['observations'] if item['adapter_id'] == 'codex_app_server')
    if state == 'old':
        row['observation_age_ms'] = 119_000
        snapshot['observation_age_ms'] = 500
    else:
        snapshot['evidence'] = []
        snapshot['availability']['availability'] = [
            item for item in snapshot['availability']['availability'] if item['adapter_id'] != 'codex_app_server']
        row.update(state=state, observation_age_ms=0 if state == 'ABSENT' else None,
                   error_code='DISCOVERY_FAILED' if state == 'FAILED' else None)
        if state == 'ABSENT':
            empty = build_executor_inventory_snapshot((), server_id='server', executor_id='executor',
                producer_instance_id='owner', publication_sequence=1)
            snapshot['availability']['availability'] = empty['availability']['availability']
    snapshot['inventory_revision'] = _revision(snapshot)
    receipt = (1, 100.0, snapshot['observation_age_ms'])
    assert inventory_is_fresh(current(snapshot), receipt, 'claude_stream', monotonic_now=101)
    assert inventory_is_fresh(current(snapshot), receipt, 'codex_app_server', monotonic_now=101) is (state == 'ABSENT')
    assert not inventory_is_fresh(current(snapshot), None, 'claude_stream', monotonic_now=101)
    assert not inventory_is_fresh(current(snapshot), (2, 100, 0), 'claude_stream', monotonic_now=101)


@pytest.mark.parametrize('change', ['none', 'candidate', 'platform', 'control', 'format'])
def test_format_two_consent_migration_preserves_selected_security_evidence(change):
    snapshot = sample()
    selected = selection(snapshot, 'codex_app_server', snapshot['evidence'][0]['candidate_ref'])
    old = copy.deepcopy(selected)
    old['format'] = 2
    if change == 'candidate':
        old['evidence']['candidate_ref'] = 'inst_' + '0' * 64
    elif change == 'platform':
        old['runtime']['implementation_platforms'] = ['other']
    elif change == 'control':
        old['runtime']['control_targeting'].append(dict(action='future', supported=True))
    elif change == 'format':
        old['format'] = 1
    assert compatible_selection(old, selected) is (change == 'none')
    assert old['format'] == (1 if change == 'format' else 2)


@pytest.mark.parametrize('state', ['PENDING', 'FAILED'])
@pytest.mark.parametrize('previously_incompatible', [False, True])
def test_partial_inventory_preserves_prior_consent_but_never_accepts_execution(bound, state, previously_incompatible):
    deps, client, headers, binding = bound
    key = ExecutorKey(binding['server_id'], binding['executor_id'])
    with deps.connection_factory.unit_of_work(write=False) as uow:
        original = json.loads(uow.connection.execute(
            'SELECT canonical_projection FROM execution_inventory_snapshots WHERE executor_id=? '
            'ORDER BY publication_sequence DESC LIMIT 1', (key.executor_id,)).fetchone()[0])
        before = dict(uow.connection.execute('SELECT * FROM execution_bindings WHERE binding_id=?',
                                             (binding['binding_id'],)).fetchone())

    sequence = original['publication_sequence']
    def publish(snapshot):
        nonlocal sequence
        sequence += 1
        snapshot = copy.deepcopy(snapshot)
        snapshot['publication_sequence'] = sequence
        snapshot['inventory_revision'] = _revision(snapshot)
        result = publish_executor_inventory(deps.connection_factory, principal=key,
            producer_instance_id=original['producer_instance_id'], snapshot=snapshot)
        client.app.state.inventory_fresh_publications[(key.server_id, key.executor_id)] = (sequence, time.monotonic(), 0)
        return result

    publish(original)  # Retain the original consent before pruning snapshots.
    with deps.connection_factory.unit_of_work() as uow:
        prior = uow.connection.execute('SELECT baseline_json FROM execution_inventory_revalidation WHERE executor_id=?',
                                      (key.executor_id,)).fetchone()
        baseline = json.loads(prior[0])
        baseline['format'] = 2  # Actual stored baseline shape before this upgrade.
        uow.connection.execute('UPDATE execution_inventory_revalidation SET baseline_json=? WHERE executor_id=?',
                               (json.dumps(baseline), key.executor_id))
    observed = copy.deepcopy(original)
    if previously_incompatible:
        observed['evidence'][0]['content_fingerprint'] = 'sha256:' + '0' * 64
    publish(observed)
    assert read(client, headers, binding).json()['state'] == ('STALE' if previously_incompatible else 'APPROVED')

    partial = copy.deepcopy(observed)
    adapter = binding['adapter_id']
    partial['evidence'] = [row for row in partial['evidence'] if row['adapter_id'] != adapter]
    partial['availability']['availability'] = [row for row in partial['availability']['availability'] if row['adapter_id'] != adapter]
    next(row for row in partial['observations'] if row['adapter_id'] == adapter).update(
        state=state, observation_age_ms=None, error_code='DISCOVERY_FAILED' if state == 'FAILED' else None)
    for _ in range(3):  # Both old publications are pruned; retained consent survives.
        publication = publish(partial)
        assert read(client, headers, binding).json()['state'] == ('STALE' if previously_incompatible else 'APPROVED')
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert not accepts_binding(uow.connection, before, publication.inventory_revision, key.server_id, key.executor_id)
            assert dict(uow.connection.execute('SELECT * FROM execution_bindings WHERE binding_id=?',
                        (binding['binding_id'],)).fetchone()) == before
    from okto_nexus.application.execution_log import read_execution_log
    log = read_execution_log(deps.connection_factory, limit=100)
    assert any(row['code'] == 'INVENTORY_OBSERVATION_' + state for row in log['items'])
    publication = publish(observed)
    assert read(client, headers, binding).json()['state'] == ('STALE' if previously_incompatible else 'APPROVED')
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert accepts_binding(uow.connection, before, publication.inventory_revision,
                               key.server_id, key.executor_id) is not previously_incompatible


@pytest.mark.parametrize('local_setup', ['codex_app_server', 'claude_stream', 'pi_rpc'], indirect=True)
def test_lease_and_intent_use_selected_adapter_age_not_sibling_age(admitted_local):
    from nexus_connector_core import R4_CONTRACT_REVISION
    from okto_nexus.application.execution_leases import ExecutionLeaseService
    from okto_nexus.errors import OktoNexusError
    setup, sent, channel, access = admitted_local
    deps, app, client, headers, _, candidate, _ = setup
    owner = app.state.embedded_inventory_owner
    sequence = owner.publication.publication_sequence

    def publish_age(selected_stale):
        nonlocal sequence
        sequence += 1
        snapshot = build_executor_inventory_snapshot(owner.candidates, server_id=owner.key.server_id,
            executor_id=owner.key.executor_id, producer_instance_id=owner.dispatcher.owner_id,
            publication_sequence=sequence)
        for row in snapshot['observations']:
            row['observation_age_ms'] = 120_000 if (row['adapter_id'] == candidate.adapter_id) == selected_stale else 0
        publish_executor_inventory(deps.connection_factory, principal=owner.key,
            producer_instance_id=owner.dispatcher.owner_id, snapshot=snapshot,
            embedded_owner=(owner.dispatcher.owner_id, owner.dispatcher.epoch, owner.generation))
        owner.fresh[(owner.key.server_id, owner.key.executor_id)] = (sequence, time.monotonic(), 0)

    leases = ExecutionLeaseService(factory=deps.connection_factory, access=access, fresh_publications=owner.fresh)
    request = dict(protocol_major=1, contract_revision=R4_CONTRACT_REVISION, type='lease.renew',
        request_id='age-proof', grant_id=sent.grant_id, expected_lease_serial=0, scope=sent.scope,
        connection_id=channel.connection_id, connection_generation=channel.connection_generation, purpose='initial')
    intent = dict(client_intent_id='age-proof', intent='runtime.start', binding_id=sent.scope['binding_id'],
                  workspace_binding_id=sent.scope['workspace_binding_id'], new_session=True)
    publish_age(True)
    with pytest.raises(OktoNexusError, match='inventory is no longer fresh'):
        leases.issue(request, channel=channel)
    stale = client.post('/v1/runtime/intents:resolve', headers=headers['subject'], json=intent)
    assert stale.status_code == 200, stale.text
    assert not stale.json()['can_submit'] and 'inventory_not_fresh' in str(stale.json())
    publish_age(False)
    granted = leases.issue(request, channel=channel)
    assert granted['type'] == 'lease.granted' and granted['scope'] == sent.scope
    ready = client.post('/v1/runtime/intents:resolve', headers=headers['subject'], json={**intent, 'client_intent_id':'age-restored'})
    assert ready.status_code == 200, ready.text
    assert ready.json()['can_submit'], ready.json()
