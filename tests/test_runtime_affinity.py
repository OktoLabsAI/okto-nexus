from dataclasses import replace

import pytest

from okto_nexus.domain.runtime_affinity import RuntimeAffinity


def affinity(policy, sender='creator', origin='verified-session', **changes):
    binding = dict(server_id='server', executor_id='host', binding_id='binding', workspace_id='workspace',
        workspace_binding_id='folder', realization_ref='config', realization_revision=1, binding_revision=1,
        session_policy=policy) | changes
    return RuntimeAffinity.for_binding(binding, sender_agent_id=sender, source_session_key=origin)


def test_shared_and_one_shot_do_not_multiply_identity_by_sender():
    for policy in ('shared', 'one_shot'):
        assert affinity(policy).opaque_key == affinity(policy, 'another', 'another-session').opaque_key


def test_per_sender_reuses_sender_unit_but_does_not_block_another_sender():
    assert affinity('per_sender').opaque_key == affinity('per_sender', origin='second-session').opaque_key
    assert affinity('per_sender').opaque_key != affinity('per_sender', sender='another').opaque_key


def test_sender_session_keeps_verified_s1_s2_s3_distinct_and_fallback_stable():
    assert len({affinity('per_sender_session', origin=s).opaque_key for s in ('s1', 's2', 's3')}) == 3
    fallback = affinity('per_sender_session', origin='')
    assert fallback.uses_origin_fallback and fallback.opaque_key == affinity('per_sender_session', origin='').opaque_key
    assert fallback.opaque_key != affinity('per_sender_session', origin='s1').opaque_key
    assert not affinity('per_sender').uses_origin_fallback


@pytest.mark.parametrize('field', ['server_id', 'executor_id', 'binding_id', 'workspace_id',
                                 'workspace_binding_id', 'configuration_key'])
def test_scope_and_configuration_cannot_share_a_reservation(field):
    current = affinity('shared')
    assert current.opaque_key != replace(current, **{field: 'different'}).opaque_key


def test_binding_revisions_and_required_sender_are_not_ignored():
    assert affinity('shared').opaque_key != affinity('shared', binding_revision=2).opaque_key
    assert affinity('shared').opaque_key != affinity('shared', realization_revision=2).opaque_key
    with pytest.raises(ValueError):
        affinity('per_sender_session', sender=None)
    with pytest.raises(ValueError):
        affinity('future')
