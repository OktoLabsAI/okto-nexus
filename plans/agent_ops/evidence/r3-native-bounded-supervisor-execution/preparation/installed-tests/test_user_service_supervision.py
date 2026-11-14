"""Pure decisions; no host processes, service effects or real waits."""
import pytest

from nexus_connector_core.user_service_supervision import (
    RestartPolicy, RetryState, record_exit, reserve_attempt)


def test_four_attempts_backoff_and_exhaustion_do_not_reset_on_successful_exit():
    state = RetryState()
    now = 100.0
    for number in range(1, 5):
        state = reserve_attempt(state, now, True)
        assert state.phase == 'running' and state.attempts_started == number
        state = record_exit(state, now + 1, 0 if number == 2 else 3, True)
        if number < 4:
            assert state.phase == 'backoff' and state.next_retry_monotonic == now + 61
            assert reserve_attempt(state, now + 60.99, True) is state
        else:
            assert state.phase == 'exhausted' and state.attempts_started == 4
            with pytest.raises(ValueError):
                reserve_attempt(state, now + 1000, True)
        now += 61


def test_stop_during_backoff_cannot_launch():
    state = record_exit(reserve_attempt(RetryState(), 0, True), 1, 3, True)
    stopped = reserve_attempt(state, 2, False)
    assert stopped.phase == 'stopped' and stopped.attempts_started == 1
    assert stopped.next_retry_monotonic is None
    with pytest.raises(ValueError):
        reserve_attempt(stopped, 1000, True)


def test_normal_stop_exit_does_not_retry():
    running = reserve_attempt(RetryState(), 0, True)
    assert record_exit(running, 1, 3, False).phase == 'stopped'


@pytest.mark.parametrize('desired', [False, True])
def test_unknown_is_not_death_or_reset_authority(desired):
    unknown = RetryState(attempts_started=1, phase='unknown')
    assert reserve_attempt(unknown, 1000, desired) is unknown
    with pytest.raises(ValueError):
        record_exit(unknown, 1000, 0, desired)


def test_reservation_prevents_a_second_launch_before_exit():
    running = reserve_attempt(RetryState(), 0, True)
    with pytest.raises(ValueError):
        reserve_attempt(running, 100, True)


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), '1'])
def test_invalid_clock_refused(value):
    with pytest.raises(ValueError):
        reserve_attempt(RetryState(), value, True)
    with pytest.raises(ValueError):
        RestartPolicy(backoff_seconds=value)


@pytest.mark.parametrize('kwargs', [
    {'attempts_started': True}, {'attempts_started': -1}, {'phase': 'ready'},
    {'phase': 'initial', 'attempts_started': 1}, {'phase': 'running'},
    {'phase': 'backoff', 'attempts_started': 1},
    {'phase': 'unknown', 'next_retry_monotonic': 1}, {'last_exit_code': True},
])
def test_malformed_state_refused(kwargs):
    with pytest.raises(ValueError):
        RetryState(**kwargs)


def test_no_restarts_policy_stops_after_initial_failure():
    policy = RestartPolicy(max_restarts=0)
    running = reserve_attempt(RetryState(), 0, True, policy=policy)
    assert record_exit(running, 1, 3, True, policy=policy).phase == 'exhausted'
