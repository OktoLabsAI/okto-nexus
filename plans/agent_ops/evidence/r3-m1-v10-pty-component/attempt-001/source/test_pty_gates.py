"""Owned synthetic Python children only; no CLI, account, service or provider."""
from io import BytesIO
import json
import os
from pathlib import Path
import time

import pytest

import protected_pty as helper

ROOT = Path(__file__).resolve().parent


def run_case(tmp_path, mode, guard, timeout=15, deadline=None):
    handoff = tmp_path / 'handoff.json'
    env = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT') if key in os.environ}
    env.update(PATH='C:/Python313;C:/Windows/System32', HOME=str(tmp_path), USERPROFILE=str(tmp_path),
               APPDATA=str(tmp_path), LOCALAPPDATA=str(tmp_path), TEMP=str(tmp_path), TMP=str(tmp_path), PYTHONUTF8='1')
    result = helper.transfer_once(
        producer_argv=['C:/Python313/python.exe', '-I', '-B', str(ROOT / 'marker_producer.py'), mode, str(handoff)],
        consumer_argv=['C:/Python313/python.exe', '-I', '-B', str(ROOT / 'marker_consumer.py'), str(handoff)],
        env=env, consumer_env={**env, 'OKTO_NEXUS_CONNECTER_DAEMON_FG': '1'},
        cwd=tmp_path, timeout_seconds=timeout, synthetic_probe=True,
        consumer_ready_marker=helper.READY_PREFIX + str(handoff), effect_guard=guard,
        deadline_monotonic=deadline)
    result['synthetic_files'] = {name: (tmp_path / name).exists() for name in
        ('producer-started.json', 'consumer-started.json', 'consumer-ack.json', 'producer-saw-ack.json')}
    raw = json.dumps(result, indent=2)
    assert not helper.KEY.search(raw)
    (tmp_path.parent / (tmp_path.name + '-result.json')).write_text(raw, encoding='utf-8')
    assert result['active_job_processes_after'] == 0
    assert result['public_ipc_readers_joined'] is True
    assert result['worker_exit'] is not None
    assert not helper.KEY.search(''.join(p.read_text(encoding='utf-8') for p in tmp_path.iterdir() if p.is_file()))
    return result


def test_cooperative_producer_waits_for_one_consumer_and_both_gates_precede_spawns(tmp_path):
    seen = []
    def guard(phase):
        seen.append(phase)
        assert not (tmp_path / (phase + '-started.json')).exists()
        if phase == 'consumer':
            assert (tmp_path / 'producer-started.json').exists()
            assert (tmp_path / 'handoff.json').exists()
        return True
    result = run_case(tmp_path, 'key-before-handoff', guard)
    assert seen == ['producer', 'consumer']
    assert result['effect_gates_requested'] == result['effect_gates_allowed'] == seen
    assert result['status'] == 'TRANSFERRED_ONCE' and not result['forced_owned_cleanup']
    assert result['producer_alive_at_consumer_start'] and result['consumer_start_count'] == 1
    assert result['consumer_material_matches'] and result['producer_exit'] == result['consumer_exit'] == 0
    assert all(result['synthetic_files'].values())
    assert all(result['tty_probe']['streams'].values()) and result['tty_probe']['visible'] is False
    assert result['producer']['exact_job_member'] and result['consumer']['exact_job_member']
    assert result['dependency_probe']['module'].endswith('winpty\\__init__.py')


@pytest.mark.parametrize('answer', [False, None, 1])
def test_non_true_producer_guard_means_no_producer_or_consumer(tmp_path, answer):
    calls = []
    def guard(phase):
        calls.append(phase)
        return answer
    result = run_case(tmp_path, 'key-before-handoff', guard)
    assert calls == ['producer'] and result['reason'] == 'EFFECT_GUARD_DENIED'
    assert result['producer_started'] is False and result['consumer_started'] is False
    assert result['possible_effect'] is False and result['delivery_attempted'] is False
    assert not any(result['synthetic_files'].values())


def test_consumer_guard_denial_preserves_possible_producer_effect_without_delivery(tmp_path):
    calls = []
    def guard(phase):
        calls.append(phase)
        return phase == 'producer'
    result = run_case(tmp_path, 'key-before-handoff', guard)
    assert calls == ['producer', 'consumer']
    assert result['status'] == 'UNCONFIRMED' and result['reason'] == 'EFFECT_GUARD_DENIED'
    assert result['possible_effect'] is True and result['producer_started'] is True
    assert result['possible_consumer_effect'] is False and result['delivery_attempted'] is False
    assert result['consumer_start_count'] == 0 and not result['synthetic_files']['consumer-started.json']


def test_guard_exception_is_denial_without_serializing_its_message(tmp_path):
    def guard(phase):
        raise ValueError('PRIVATE ACCOUNT VALUE NEVER PUBLIC')
    result = run_case(tmp_path, 'key-before-handoff', guard)
    assert result['producer_started'] is False and result['delivery_attempted'] is False
    assert result['effect_guard_decisions'] == [{'phase': 'producer', 'allowed': False, 'error_type': 'ValueError'}]
    assert 'PRIVATE ACCOUNT' not in json.dumps(result)


def test_allow_returning_after_deadline_cannot_start_producer(tmp_path):
    def guard(phase):
        time.sleep(1.1)
        return True
    result = run_case(tmp_path, 'key-before-handoff', guard, timeout=1)
    assert result['status'] != 'TRANSFERRED_ONCE'
    assert not any(result['synthetic_files'].values())
    assert not any(d['allowed'] for d in result['effect_guard_decisions'])


def test_missing_handoff_marker_expires_without_consumer_gate_or_delivery(tmp_path):
    seen = []
    result = run_case(tmp_path, 'marker-absent', lambda phase: seen.append(phase) or True, timeout=4)
    assert seen == ['producer'] and result['status'] != 'TRANSFERRED_ONCE'
    assert result['synthetic_files']['producer-started.json']
    assert not result['synthetic_files']['consumer-started.json']
    assert not result['synthetic_files']['consumer-ack.json']


def test_shared_deadline_cannot_be_extended_by_new_helper_timeout(tmp_path):
    result = run_case(tmp_path, 'key-before-handoff', lambda phase: time.sleep(1.1) or True,
                      timeout=15, deadline=time.monotonic() + 1)
    assert result['status'] != 'TRANSFERRED_ONCE'
    assert not any(result['synthetic_files'].values())
    assert not any(d['allowed'] for d in result['effect_guard_decisions'])


@pytest.mark.parametrize('frames', [
    [{'kind': 'effect_gate', 'phase': 'consumer', 'sequence': 2}],
    [{'kind': 'effect_gate', 'phase': 'producer', 'sequence': True}],
    [{'kind': 'effect_gate', 'phase': 'producer', 'sequence': 1, 'secret': 'not allowed'}],
    [{'kind': 'effect_gate', 'phase': 'producer', 'sequence': 1},
     {'kind': 'effect_gate', 'phase': 'producer', 'sequence': 1}],
    [{'kind': 'effect_gate', 'phase': 'producer', 'sequence': 1},
     {'kind': 'effect_gate', 'phase': 'consumer', 'sequence': 2}],
])
def test_malformed_out_of_order_or_post_denial_gate_never_authorizes(frames):
    protocol = helper._Protocol()
    with pytest.raises(helper.TransferError):
        for frame in frames:
            protocol.gate(frame)
            # No allow reply was issued. A consumer cannot follow that denial.
    assert protocol.allowed == []


@pytest.mark.parametrize('reply', [
    {'kind': 'effect_gate_reply', 'phase': 'consumer', 'sequence': 1, 'allow': True},
    {'kind': 'effect_gate_reply', 'phase': 'producer', 'sequence': 2, 'allow': True},
    {'kind': 'effect_gate_reply', 'phase': 'producer', 'sequence': 1, 'allow': 1},
])
def test_worker_rejects_reply_for_wrong_phase_sequence_or_boolean(reply):
    with pytest.raises(helper.TransferError):
        helper._reply_allowed(reply, 'producer', 1)


def test_protocol_refuses_duplicate_json_keys_and_oversized_line():
    with pytest.raises(helper.TransferError):
        helper._json(b'{"allow":false,"allow":true}')
    reader = helper._Lines(BytesIO(b'x' * 17 + b'\n'), limit=16, total=32)
    reader.thread.join(1)
    with pytest.raises(helper.TransferError):
        reader.next(time.monotonic() + 1)


def test_absent_guard_is_refused_before_job_or_process(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail('No Job or process may exist without an explicit guard')
    monkeypatch.setattr(helper, 'Job', forbidden)
    monkeypatch.setattr(helper.subprocess, 'Popen', forbidden)
    with pytest.raises(ValueError, match='explicit effect guard'):
        helper.transfer_once(producer_argv=['C:/Python313/python.exe'],
            consumer_argv=['C:/Python313/python.exe'], env={}, cwd=tmp_path)


def test_expired_shared_deadline_refuses_before_job_or_process(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail('An expired phase must not create an auxiliary process')
    monkeypatch.setattr(helper, 'Job', forbidden)
    monkeypatch.setattr(helper.subprocess, 'Popen', forbidden)
    with pytest.raises(helper.TransferError, match='TRANSFER_DEADLINE'):
        helper.transfer_once(producer_argv=['C:/Python313/python.exe'],
            consumer_argv=['C:/Python313/python.exe'], env={}, cwd=tmp_path,
            effect_guard=lambda phase: True, deadline_monotonic=time.monotonic() - 1)
