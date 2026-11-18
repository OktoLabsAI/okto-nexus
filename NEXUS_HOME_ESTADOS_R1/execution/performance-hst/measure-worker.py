"""Measurement-only guard override; builder and dataset bytes stay unchanged."""
from contextlib import contextmanager
import hashlib
import importlib.util
from pathlib import Path
import socket
import subprocess
import sys
import threading


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('hst_perf_frozen_builder', HERE / 'benchmark.py')
benchmark = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = benchmark
spec.loader.exec_module(benchmark)


@contextmanager
def guarded():
    popen, connect, connect_ex, socketpair, sendto = (
        subprocess.Popen, socket.socket.connect, socket.socket.connect_ex, socket.socketpair, socket.socket.sendto)
    local = threading.local()

    def forbidden(*args, **kwargs):
        raise RuntimeError('External process/network effects are prohibited in this measurement worker.')

    class ForbiddenProcess(popen):
        def __init__(self, *args, **kwargs):
            forbidden()

    def pair(*args, **kwargs):
        depth = getattr(local, 'depth', 0)
        local.depth = depth + 1
        try:
            return socketpair(*args, **kwargs)
        finally:
            local.depth = depth

    def permitted(address):
        return (getattr(local, 'depth', 0) > 0 and isinstance(address, tuple)
                and address[0] in ('127.0.0.1', '::1'))

    def scoped_connect(sock, address):
        if permitted(address):
            return connect(sock, address)
        forbidden()

    def scoped_connect_ex(sock, address):
        if permitted(address):
            return connect_ex(sock, address)
        forbidden()

    subprocess.Popen = ForbiddenProcess
    socket.socket.connect, socket.socket.connect_ex = scoped_connect, scoped_connect_ex
    socket.socketpair, socket.socket.sendto = pair, forbidden
    try:
        yield
    finally:
        subprocess.Popen = popen
        socket.socket.connect, socket.socket.connect_ex = connect, connect_ex
        socket.socketpair, socket.socket.sendto = socketpair, sendto


original_measure = benchmark.measure


def measured(*args, **kwargs):
    result = original_measure(*args, **kwargs)
    result['measurement_guard'] = dict(source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Popen blocked; connect/connect_ex/sendto blocked except original Windows socketpair local wakeup inside current-thread depth fence')
    return result


benchmark.no_external_effects = guarded
benchmark.measure = measured
benchmark.main()
