"""Windows birth proof: real self-process reads plus targeted OS failure fences."""
import os
import sys

import pytest

from okto_nexus.adapters.outbound.observation import windows_identity as windows
from okto_nexus.domain.herdr_observations import HerdrObservationError, WindowsProcessIdentity


IDENTITY = WindowsProcessIdentity('1' * 64, 42, 123456789012345678, r'C:\fixture\native.exe')


@pytest.mark.skipif(sys.platform != 'win32', reason='Qualified Windows-only OS adapter')
def test_real_self_process_birth_is_integer_alive_and_guard_closes():
    first_host = windows.local_host_id()
    assert len(first_host) == 64 and first_host == windows.local_host_id()
    with windows.open_process_identity(os.getpid()) as guard:
        first = guard.identity
        assert first.pid == os.getpid() and first.host_id == first_host
        assert type(first.creation_filetime) is int and first.creation_filetime > 0
        assert guard.require_alive() == first
        assert windows.read_process_identity(os.getpid()) == first
    with pytest.raises(HerdrObservationError, match='HERDR_PROCESS_GUARD_CLOSED'):
        guard.require_alive()


def test_non_windows_is_explicitly_unsupported(monkeypatch):
    monkeypatch.setattr(windows.sys, 'platform', 'linux')
    with pytest.raises(HerdrObservationError, match='HERDR_LOCAL_WINDOWS_REQUIRED'):
        windows.local_host_id()


@pytest.mark.parametrize('pid', [True, 0, -1, 1 << 32, '42'])
def test_bad_pid_rejected_before_os_access(pid, monkeypatch):
    monkeypatch.setattr(windows, 'local_host_id', lambda: pytest.fail('host access on invalid PID'))
    with pytest.raises(HerdrObservationError, match='HERDR_PROCESS_IDENTITY_UNAVAILABLE'):
        with windows.open_process_identity(pid):
            pytest.fail('invalid PID admitted')


class Kernel:
    def __init__(self, handle=7):
        self.handle = handle
        self.closed = []
        self.calls = []

    def OpenProcess(self, access, inherit, pid):
        self.calls.append((access, inherit, pid))
        return self.handle

    def CloseHandle(self, handle):
        self.closed.append(handle)


def kernel(monkeypatch, *, handle=7):
    result = Kernel(handle)
    monkeypatch.setattr(windows, 'local_host_id', lambda: IDENTITY.host_id)
    monkeypatch.setattr(windows, '_kernel', lambda: result)
    return result


def test_access_denied_is_unavailable_not_pid_fallback(monkeypatch):
    api = kernel(monkeypatch, handle=0)
    with pytest.raises(HerdrObservationError, match='HERDR_PROCESS_IDENTITY_UNAVAILABLE'):
        with windows.open_process_identity(42):
            pytest.fail('denied process admitted')
    assert api.closed == []
    assert api.calls == [(0x101000, False, 42)]


def test_handle_closed_on_initial_query_failure(monkeypatch):
    api = kernel(monkeypatch)

    def denied(*args, **kwargs):
        raise HerdrObservationError('HERDR_PROCESS_IDENTITY_UNAVAILABLE')

    monkeypatch.setattr(windows, '_facts', denied)
    with pytest.raises(HerdrObservationError, match='HERDR_PROCESS_IDENTITY_UNAVAILABLE'):
        with windows.open_process_identity(42):
            pytest.fail('missing birth admitted')
    assert api.closed == [7]


def test_identity_change_mid_bracket_and_caller_failure_always_close_handle(monkeypatch):
    api = kernel(monkeypatch)
    identities = iter([IDENTITY, WindowsProcessIdentity(IDENTITY.host_id, 42, IDENTITY.creation_filetime + 1, IDENTITY.image_path)])
    monkeypatch.setattr(windows, '_facts', lambda *args, **kwargs: next(identities))
    with pytest.raises(HerdrObservationError, match='HERDR_PROCESS_IDENTITY_CHANGED'):
        with windows.open_process_identity(42) as guard:
            guard.require_alive()
    assert api.closed == [7]
    monkeypatch.setattr(windows, '_facts', lambda *args, **kwargs: IDENTITY)
    with pytest.raises(RuntimeError, match='cancel bracket'):
        with windows.open_process_identity(42):
            raise RuntimeError('cancel bracket')
    assert api.closed == [7, 7]


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows registry boundary')
def test_machine_guid_failure_does_not_fallback_to_host_alias_or_echo_raw_value(monkeypatch):
    import winreg

    def denied(*args, **kwargs):
        raise OSError('PRIVATE GUID OR HOST DETAILS')

    monkeypatch.setattr(winreg, 'OpenKey', denied)
    with pytest.raises(HerdrObservationError) as error:
        windows.local_host_id()
    assert error.value.code == 'HERDR_HOST_ID_UNAVAILABLE'
    assert 'PRIVATE' not in str(error.value)
