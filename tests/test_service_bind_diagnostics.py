"""Listener diagnostics classify the actual failure, never arbitrary text."""
import asyncio
import errno
import socket

from okto_nexus.adapters.inbound.cli.serve import _bind_failure_code
from okto_nexus.adapters.outbound.service_manager.logs import ServiceLog, read_logs


def test_bind_conflict_has_a_coded_diagnostic_without_exception_text(tmp_path):
    async def conflict():
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            try:
                await asyncio.get_running_loop().create_server(
                    asyncio.Protocol, host='127.0.0.1', port=listener.getsockname()[1])
            except OSError:
                try:
                    # The same context-preserving conversion used by Uvicorn.
                    raise SystemExit(1)
                except SystemExit as failure:
                    return _bind_failure_code(failure)
        raise AssertionError('The occupied listener unexpectedly accepted another bind')

    code = asyncio.run(conflict())
    assert code == 'PORT_IN_USE'
    log = ServiceLog(tmp_path, generation='1' * 32, supervisor='detached')
    log.write(code, state='STARTING')
    log.close()
    report, _ = read_logs(tmp_path)
    assert [event['code'] for event in report['events']] == ['PORT_IN_USE']
    assert all(event['error_code'] is None for event in report['events'])


def test_unrelated_startup_errors_are_not_misreported_as_listener_failures():
    for failure in (PermissionError(errno.EACCES, 'private-sentinel'),
                    OSError(errno.EADDRINUSE, 'private-sentinel'),
                    RuntimeError('bind failed private-sentinel'), SystemExit(1)):
        assert _bind_failure_code(failure) is None
