"""Grant deadlines are instants across canonical commands and passive reads."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import test_attention_native as native

from okto_nexus.application.execution_native_facts import grant_candidate_matches, stamp
from okto_nexus.domain.base import iso_plus
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError

opening = native.opening
isolated_native_inventory = native.isolated_native_inventory


def formatted(instant, style):
    zone = timezone(timedelta(hours=-3)) if style == '-03:00' else timezone.utc
    result = instant.astimezone(zone).isoformat(timespec='microseconds')
    return result.replace('+00:00', 'Z') if style == 'Z' else result


@pytest.mark.parametrize('expiry_style', ['Z', '+00:00', '-03:00'])
@pytest.mark.parametrize('now_style', ['Z', '+00:00', '-03:00'])
@pytest.mark.parametrize('delta_us', [-1, 0, 1])
def test_grant_expiry_uses_instant_at_microsecond_boundary(expiry_style, now_style, delta_us):
    deadline = datetime(2026, 11, 6, 15, 0, tzinfo=timezone.utc)
    grant = dict(grant_id='grant', endpoint_id='endpoint', credential_binding='key', no_expiry=False,
        expires_at=formatted(deadline, expiry_style), actions=['send'])
    context = RuntimeRequestContext('delegate', 'agent_key', credential_binding='key', execution_grant_id='grant')
    assert grant_candidate_matches(grant, context=context, actor=SimpleNamespace(api_key_hash='key'),
        action='send', endpoint_id='endpoint', now=formatted(deadline + timedelta(microseconds=delta_us), now_style)
    ) is (delta_us < 0)


def test_canonical_delegated_authorization_matches_each_passive_deadline_representation(opening, monkeypatch):
    # The grant and distinct represented/calling identities use the canonical
    # service and repository; only the clock is controlled, without a sleep.
    deps, _, access, operator, _, _, _, _ = opening
    issued = access.issue(operator, actor_agent_id='other', endpoint_id='ep', actions=['send'],
        expires_at=iso_plus(deps.clock.now_iso(), 60))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        actor = access.agents.get(uow, 'other')
        grant, = access.grants.candidates(uow, actor_id='other', endpoint_id='ep')
    assert grant['grant_id'] == issued['grant_id'] and grant['represented_agent_id'] == 'subject'
    context = RuntimeRequestContext('other', 'agent_key', credential_binding=actor.api_key_hash,
        execution_grant_id=grant['grant_id'])
    deadline = stamp(grant['expires_at'])
    with monkeypatch.context() as controlled:
        for delta_us in (-1, 0, 1):
            observed = deadline + timedelta(microseconds=delta_us)
            controlled.setattr(deps.clock, 'now_iso', lambda value=formatted(observed, 'Z'): value)
            with deps.connection_factory.unit_of_work(write=False) as uow:
                if delta_us < 0:
                    selected = access.authorize(context, action='send', endpoint_id='ep',
                        represented_agent_id='subject', uow=uow, audit=False, check_budget=False)
                    assert selected['grant_id'] == issued['grant_id']
                else:
                    with pytest.raises(OktoNexusError) as error:
                        access.authorize(context, action='send', endpoint_id='ep',
                            represented_agent_id='subject', uow=uow, audit=False, check_budget=False)
                    assert str(error.value.code) == 'PERMISSION_DENIED'
            for style in ('Z', '+00:00', '-03:00'):
                assert grant_candidate_matches(grant, context=context, actor=actor, action='send',
                    endpoint_id='ep', now=formatted(observed, style)) is (delta_us < 0)
