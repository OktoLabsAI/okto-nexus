"""Succession policy: a newer binary takes over an approved ref only under `follow`."""
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_local_realization import local_setup  # noqa: F401
from test_local_launch import admitted_local  # noqa: F401
from nexus_connector_core.discovery import fingerprint
from nexus_connector_core.availability import effective_installation_ref
from okto_nexus.application import execution_local_observations as observations
from okto_nexus.application.execution_installation_succession import (
    accept_succession, apply_update_policy, effective_policy, parse_version)
from okto_nexus.application.execution_inventory_revalidation import (
    accepts_binding, same_installation_location)
from okto_nexus.application.execution_local_launch import ApprovedLocalLaunch
from okto_nexus.bootstrap import embedded_inventory


class World:
    """The admitted approved binding, its consent version and a probe stub."""

    def __init__(self, admitted, monkeypatch, hub='follow', consent_version='2.1.309'):
        self.setup, self.sent, _, _ = admitted
        self.deps, self.app, self.client, _, _, self.candidate, self.tmp = self.setup
        self.owner = self.app.state.embedded_inventory_owner
        self.key = self.owner.key
        self.stable = effective_installation_ref(self.candidate)
        self.probed, self.probe_version = [], '2.1.310'
        self.notices = []
        self.client.portal.call(self.owner.refresh)
        self.shim = SimpleNamespace(connection_factory=self.deps.connection_factory, clock=self.deps.clock,
                                    config=SimpleNamespace(runtime_update_policy=hub))
        with self.deps.connection_factory.unit_of_work() as uow:
            row = uow.connection.execute('SELECT realization_ref,local_record_json FROM execution_local_realizations').fetchone()
            record = json.loads(row['local_record_json'])
            record['candidate']['version'] = consent_version
            uow.connection.execute('UPDATE execution_local_realizations SET local_record_json=?',
                                   (json.dumps(record),))
        world = self

        async def probe(selected):
            world.probed.append(selected)
            if isinstance(world.probe_version, Exception):
                raise world.probe_version
            return replace(selected, version=world.probe_version)
        monkeypatch.setattr(observations, 'probe_version', probe)

    def successor(self, name='codex2.exe', directory=None, **changes):
        folder = Path(directory) if directory else Path(self.candidate.executable).parent
        folder.mkdir(exist_ok=True)
        binary = folder / name
        binary.write_bytes(b'Newer harness release ' + name.encode())
        return replace(self.candidate, executable=str(binary), fingerprint=fingerprint(binary), **changes)

    def run(self, candidates):
        return apply_update_policy(self.shim, self.key, candidates, self.notices.append)

    def rows(self):
        with self.deps.connection_factory.unit_of_work(write=False) as uow:
            return [dict(r) for r in uow.connection.execute(
                'SELECT * FROM execution_installation_succession ORDER BY id')]


@pytest.fixture
def world(admitted_local, monkeypatch):
    return World(admitted_local, monkeypatch)


def test_follow_relabels_one_newer_successor_and_is_idempotent(world):
    new = world.successor()
    result = world.run((new,))
    assert [effective_installation_ref(c) for c in result] == [world.stable]
    assert result[0].executable == new.executable
    rows = world.rows()
    assert len(rows) == 1 and rows[0]['decision'] == 'accepted' and rows[0]['reason'] == 'newer_version'
    assert (rows[0]['from_version'], rows[0]['to_version'], rows[0]['policy'], rows[0]['policy_source']) == \
        ('2.1.309', '2.1.310', 'follow', 'hub')
    assert rows[0]['stable_ref'] == world.stable and len(world.notices) == 1
    with world.deps.connection_factory.unit_of_work(write=False) as uow:
        saved = uow.connection.execute('SELECT candidate_ref,version FROM execution_local_observations').fetchone()
    assert tuple(saved) == (world.stable, '2.1.310')
    again = world.run((new,))
    assert [effective_installation_ref(c) for c in again] == [world.stable]
    assert len(world.rows()) == 1 and len(world.notices) == 1 and len(world.probed) == 1


def held_cases(world):
    other = world.tmp / 'other'
    return {
        'downgrade': (lambda: world.successor(), '2.1.308'),
        'same_version_new_bytes': (lambda: world.successor(), '2.1.309'),
        'version_unparseable': (lambda: world.successor(), 'next'),
        'other_parent': (lambda: world.successor(directory=other), '2.1.310'),
        'architecture_mismatch': (lambda: world.successor(architecture='other'), '2.1.310'),
        'untrusted': (lambda: world.successor(trust='untrusted'), '2.1.310'),
        'probe_failed': (lambda: world.successor(), OSError('probe failed')),
    }


@pytest.mark.parametrize('reason', ['downgrade', 'same_version_new_bytes', 'version_unparseable', 'other_parent',
                                    'architecture_mismatch', 'untrusted', 'probe_failed', 'ambiguous_successors'])
def test_follow_holds_unsafe_successors(world, reason):
    if reason == 'ambiguous_successors':
        candidates = (world.successor('a.exe'), world.successor('b.exe'))
    else:
        make, world.probe_version = held_cases(world)[reason]
        candidates = (make(),)
    assert world.run(candidates) == candidates
    rows = world.rows()
    assert [(r['decision'], r['reason']) for r in rows] == [('held', reason)]
    assert len(world.notices) == 1
    world.run(candidates)
    assert len(world.rows()) == 1 and len(world.notices) == 1


def test_review_holds_without_probe_and_notifies_once(admitted_local, monkeypatch):
    world = World(admitted_local, monkeypatch, hub='review')
    candidates = (world.successor(),)
    assert world.run(candidates) == candidates
    world.run(candidates)
    assert [(r['decision'], r['reason'], r['policy']) for r in world.rows()] == [('held', 'policy_review', 'review')]
    assert len(world.notices) == 1 and world.probed == []


def test_most_restrictive_binding_wins(world):
    with world.deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        binding = dict(conn.execute('SELECT * FROM execution_bindings').fetchone())
        endpoint = dict(conn.execute('SELECT * FROM agent_endpoints WHERE endpoint_id=?', (binding['endpoint_id'],)).fetchone())
        ep = dict(endpoint, endpoint_id='second_endpoint', runtime_update_policy='review')
        b = dict(binding, endpoint_id='second_endpoint', binding_id='second_binding')
        for table, values in (('agent_endpoints', ep), ('execution_bindings', b)):
            conn.execute(f'INSERT INTO {table} (' + ','.join(values) + ') VALUES (' + ','.join('?' for _ in values) + ')',
                         tuple(values.values()))
    candidates = (world.successor(),)
    assert world.run(candidates) == candidates
    assert [(r['reason'], r['policy'], r['policy_source']) for r in world.rows()] == [('policy_review', 'review', 'endpoint')]
    assert world.probed == []
    assert effective_policy([{'runtime_update_policy': None}, {'runtime_update_policy': 'follow'}], 'follow') == ('follow', 'endpoint')


def test_operator_accept_relabels_on_next_call_without_probe(admitted_local, monkeypatch):
    world = World(admitted_local, monkeypatch, hub='review')
    candidates = (world.successor(),)
    world.run(candidates)
    held = world.rows()[0]
    with world.deps.connection_factory.unit_of_work() as uow:
        accepted = accept_succession(uow.connection, held['id'], 'operator')
    assert accepted['decision'] == 'accepted' and accepted['decided_by'] == 'operator'
    result = world.run(candidates)
    assert [effective_installation_ref(c) for c in result] == [world.stable]
    assert world.probed == [] and len(world.rows()) == 2


def test_parse_version():
    assert parse_version('2.1.310') > parse_version('2.1.99') and parse_version('2.1') < parse_version('2.1.1')
    assert parse_version('2.1.x') is None and parse_version(None) is None


def _stored():
    return {'adapter_id': 'claude_stream', 'executable': '/v/claude/2.1.309', 'fingerprint': 'f1', 'source': 'x',
            'trust': 'selected', 'version': '1', 'architecture': 'arm64', 'launch_script': None,
            'build_identity': 'b1', 'installation_ref': 'inst_1'}


def test_same_installation_location_accepts_a_relabeled_sibling_only():
    stored = _stored()
    sibling = {**stored, 'executable': '/v/claude/2.1.310', 'fingerprint': 'f2'}
    assert same_installation_location(stored, sibling)
    assert not same_installation_location(stored, {**sibling, 'executable': '/w/claude/2.1.310'})
    assert not same_installation_location(stored, {**sibling, 'installation_ref': 'inst_2'})
    assert not same_installation_location(stored, {**sibling, 'architecture': 'x86_64'})
    assert not same_installation_location(stored, {**sibling, 'launch_script': '/s.js'})
    assert not same_installation_location({**stored, 'installation_ref': None}, sibling)


def _refresh(world, monkeypatch, candidates):
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
        lambda **kw: SimpleNamespace(candidates=tuple(c for c in candidates
                                                      if not kw.get('adapter_ids') or c.adapter_id in kw['adapter_ids'])))
    world.client.portal.call(world.owner.refresh)


def _validation(world):
    with world.deps.connection_factory.unit_of_work(write=False) as uow:
        binding = uow.connection.execute('SELECT * FROM execution_bindings').fetchone()
        row = uow.connection.execute('SELECT reason,compatible FROM execution_inventory_revalidation').fetchone()
        accepted = accepts_binding(uow.connection, binding, world.owner.publication.inventory_revision,
                                   world.key.server_id, world.key.executor_id)
    return tuple(row), accepted


def test_follow_keeps_the_binding_through_a_real_refresh(admitted_local, monkeypatch):
    world = World(admitted_local, monkeypatch)
    with world.deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET runtime_update_policy='follow'")
    new = world.successor()
    _refresh(world, monkeypatch, (new,))
    assert _validation(world) == (('installation_updated', 1), True)
    launch = ApprovedLocalLaunch(world.owner, world.sent.scope)
    assert launch.candidate.executable == new.executable and launch.candidate.version == '2.1.310'
    launch.check()
    assert len(world.probed) == 1
    _refresh(world, monkeypatch, (new,))
    assert _validation(world) == (('installation_updated', 1), True) and len(world.probed) == 1
    assert [r['decision'] for r in world.rows()] == ['accepted']


def test_review_still_contains_the_binding_on_update(admitted_local, monkeypatch):
    world = World(admitted_local, monkeypatch)
    with world.deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET runtime_update_policy='review'")
    _refresh(world, monkeypatch, (world.successor(),))
    assert _validation(world) == (('installation_missing', 0), False)
    with pytest.raises(Exception):
        ApprovedLocalLaunch(world.owner, world.sent.scope).check()
    assert [(r['decision'], r['reason']) for r in world.rows()] == [('held', 'policy_review')]


def test_in_place_update_writes_an_audit_row(admitted_local, monkeypatch):
    world = World(admitted_local, monkeypatch)
    world.probe_version = '0.999.0'
    changed = replace(world.candidate, version='0.999.0')
    _refresh(world, monkeypatch, (changed,))
    assert _validation(world) == (('installation_updated', 1), True)
    assert [(r['decision'], r['reason'], r['policy'], r['to_version']) for r in world.rows()] == \
        [('accepted', 'installation_updated', 'in_place', '0.999.0')]


def _inbox(world):
    with world.deps.connection_factory.unit_of_work(write=False) as uow:
        return [r['body'] for r in uow.connection.execute(
            "SELECT m.body FROM message_deliveries d JOIN messages m USING(message_id) "
            "WHERE d.recipient_agent_id='operator' AND m.message_id LIKE 'msg_installation_update_%'")]


def test_real_refresh_sends_one_operator_notice_for_follow(admitted_local, monkeypatch):
    world = World(admitted_local, monkeypatch)
    with world.deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET runtime_update_policy='follow'")
    new = world.successor()
    _refresh(world, monkeypatch, (new,))
    _refresh(world, monkeypatch, (new,))
    inbox = _inbox(world)
    assert len(inbox) == 1 and 'Decision: accepted' in inbox[0] and '2.1.309 to 2.1.310' in inbox[0]


def test_in_place_update_sends_one_operator_notice(admitted_local, monkeypatch):
    world = World(admitted_local, monkeypatch)
    world.probe_version = '0.999.0'
    changed = replace(world.candidate, version='0.999.0')
    _refresh(world, monkeypatch, (changed,))
    _refresh(world, monkeypatch, (changed,))
    inbox = _inbox(world)
    assert len(inbox) == 1 and 'Decision: accepted' in inbox[0] and 'to 0.999.0' in inbox[0]


def test_accept_route_is_operator_only_and_refuses_trust_rule_holds(admitted_local, monkeypatch):
    world = World(admitted_local, monkeypatch, hub='review')
    headers = world.setup[3]
    candidates = (world.successor(),)
    world.run(candidates)
    held = world.rows()[0]
    path = f"/v1/connections/installation-successions/{held['id']}:accept"
    assert world.client.post(path, headers=headers['subject']).status_code == 403
    assert world.client.post('/v1/connections/installation-successions/999:accept',
                             headers=headers['operator']).status_code == 404
    accepted = world.client.post(path, headers=headers['operator'])
    assert accepted.status_code == 200, accepted.text
    assert (accepted.json()['decision'], accepted.json()['reason']) == ('accepted', 'operator_accepted')
    assert [effective_installation_ref(c) for c in world.run(candidates)] == [world.stable]
    assert world.client.post(path, headers=headers['operator']).status_code == 200
    assert len(world.rows()) == 2
    other = world.successor('other.exe', directory=world.tmp / 'other', build_identity='other-build')
    world.run((other,))
    trust = next(r for r in world.rows() if r['reason'] == 'other_parent')
    refused = world.client.post(f"/v1/connections/installation-successions/{trust['id']}:accept",
                                headers=headers['operator'])
    assert refused.status_code == 409 and 'other_parent' in refused.text
