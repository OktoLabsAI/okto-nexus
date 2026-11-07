"""Bounded retained setup history never prunes or impairs existing recovery."""
from copy import deepcopy

import pytest

import test_remote_setup_server as server
from okto_nexus.adapters.outbound.sqlite.remote_setup_repo import (
    MAX_ROOTS_PER_ACTOR, MAX_REVIEWS_PER_ROOT,
)
from okto_nexus.application.remote_setup_contract import build_review
from okto_nexus.application.terminal_connection import document_revision
from okto_nexus.errors import ErrorCode, OktoNexusError


env = server.env
template = server.template


def fill_root_capacity(env, review):
    """Fixture metadata only; no identity, credential or execution is created."""
    with env.factory.unit_of_work() as uow:
        for index in range(1, MAX_ROOTS_PER_ACTOR):
            draft = dict(review['draft'], setup_run_id=f'retained-{index}')
            selection = deepcopy(review['selection'])
            selection['identity']['agent_id'] = f'uncreated-{index}'
            item = build_review(draft, selection)
            env.deps.repos.remote_setup.save_review(uow, actor='operator', review=item,
                request_hash=document_revision(item['draft']), expected_revision=None,
                now=env.deps.clock.now_iso())


def test_root_capacity_is_per_actor_and_existing_bootstrap_replay_remains_available(env):
    body = server.request()
    review = env.service.review(env.context, body)['review']
    ref = dict(setup_run_id='remote-one', review_revision=review['review_revision'])
    original = env.service.bootstrap(env.context, ref)
    fill_root_capacity(env, review)
    before = server.snapshot(env)
    with pytest.raises(OktoNexusError) as caught:
        env.service.review(env.context, server.request(root='beyond-capacity', agent='another-unused'))
    assert caught.value.code == ErrorCode.QUOTA_EXCEEDED
    assert caught.value.details['reason'] == 'REMOTE_SETUP_ROOT_CAPACITY'
    assert caught.value.details['limit'] == 1024
    assert server.snapshot(env) == before
    assert env.service.review(env.context, body)['review'] == review
    for action in (env.service.recover, env.service.bootstrap):
        value = action(env.context, ref)
        assert value['bootstrap'] == original['bootstrap']
        assert value['material'] is None and value['material_status'] == 'unavailable'
    assert server.snapshot(env) == before
    # The repository's quota namespace does not borrow another actor's budget.
    # Authorization to create a review is covered by service/TCP tests.
    with env.factory.unit_of_work() as uow:
        env.deps.repos.remote_setup.save_review(uow, actor='second-operator', review=review,
            request_hash=document_revision(body), expected_revision=None, now=env.deps.clock.now_iso())
        assert uow.connection.execute("SELECT COUNT(*) FROM remote_setup_runs WHERE actor_agent_id='operator'").fetchone()[0] == 1024
        assert uow.connection.execute("SELECT COUNT(*) FROM remote_setup_runs WHERE actor_agent_id='second-operator'").fetchone()[0] == 1


def test_revision_capacity_preserves_pointer_even_when_caller_catches_and_commits(env):
    body = server.request()
    review = env.service.review(env.context, body)['review']
    for index in range(1, MAX_REVIEWS_PER_ROOT):
        body['expected_review_revision'] = review['review_revision']
        body['draft']['configuration']['alias'] = f'Review {index}'
        review = env.service.review(env.context, body)['review']
    before = server.snapshot(env)
    # Response loss on the 32nd revision is recoverable using the exact old CAS
    # and body. It must not attempt to allocate a 33rd retained revision.
    assert env.service.review(env.context, body)['review'] == review
    assert server.snapshot(env) == before
    proposed_draft = deepcopy(review['draft'])
    proposed_draft['configuration']['alias'] = 'Beyond capacity'
    proposed = build_review(proposed_draft, review['selection'])
    with env.factory.unit_of_work() as uow:
        with pytest.raises(OktoNexusError) as caught:
            env.deps.repos.remote_setup.save_review(uow, actor='operator', review=proposed,
                request_hash=document_revision(proposed_draft), expected_revision=review['review_revision'],
                now=env.deps.clock.now_iso())
        assert caught.value.code == ErrorCode.QUOTA_EXCEEDED
        assert caught.value.details == {'reason': 'REMOTE_SETUP_REVIEW_CAPACITY', 'limit': 32}
        assert uow.connection.execute('SELECT current_review_revision FROM remote_setup_runs').fetchone()[0] == review['review_revision']
        assert uow.connection.execute('SELECT COUNT(*) FROM remote_setup_reviews').fetchone()[0] == 32
        # An explicit successful writer commit proves the pointer assertion did
        # not depend on the exception rolling back the enclosing transaction.
        uow.connection.execute("INSERT INTO settings(key,value,updated_at) VALUES('capacity-test','true',?)", (env.deps.clock.now_iso(),))
    recovered = env.service.recover(env.context, {'setup_run_id': 'remote-one'})
    assert recovered['review'] == review and recovered['state'] == 'reviewed'
    ref = dict(setup_run_id='remote-one', review_revision=review['review_revision'])
    first = env.service.bootstrap(env.context, ref)
    assert first['material_status'] == 'issued_once'
    repeated = env.service.bootstrap(env.context, ref)
    assert repeated['bootstrap'] == first['bootstrap'] and repeated['material'] is None
    with env.factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM remote_setup_reviews').fetchone()[0] == 32


def test_revision_cap_does_not_advance_service_current_pointer(env):
    body = server.request()
    review = env.service.review(env.context, body)['review']
    for index in range(1, MAX_REVIEWS_PER_ROOT):
        body['expected_review_revision'] = review['review_revision']
        body['draft']['configuration']['alias'] = f'Review {index}'
        review = env.service.review(env.context, body)['review']
    body['expected_review_revision'] = review['review_revision']
    body['draft']['configuration']['alias'] = 'Uncommitted revision'
    before = server.snapshot(env)
    with pytest.raises(OktoNexusError) as caught:
        env.service.review(env.context, body)
    assert caught.value.code == ErrorCode.QUOTA_EXCEEDED
    assert server.snapshot(env) == before
    current = env.service.recover(env.context, {'setup_run_id': 'remote-one'})
    assert current['review']['review_revision'] == review['review_revision']
