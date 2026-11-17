"""No external effects; permit only Windows asyncio's internal socketpair."""
from contextlib import contextmanager
import socket
import subprocess
import threading


@contextmanager
def guarded():
    popen, connect, connect_ex, pair, sendto = subprocess.Popen, socket.socket.connect, socket.socket.connect_ex, socket.socketpair, socket.socket.sendto
    local = threading.local()

    def forbidden(*args, **kwargs):
        raise RuntimeError('External process/network effects are prohibited.')

    class ForbiddenProcess(popen):
        def __init__(self, *args, **kwargs):
            forbidden()

    def socketpair(*args, **kwargs):
        previous = getattr(local, 'depth', 0)
        local.depth = previous + 1
        try:
            return pair(*args, **kwargs)
        finally:
            local.depth = previous

    def allowed(address):
        return getattr(local, 'depth', 0) > 0 and isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1')

    def scoped_connect(sock, address):
        if allowed(address):
            return connect(sock, address)
        forbidden()

    def scoped_connect_ex(sock, address):
        if allowed(address):
            return connect_ex(sock, address)
        forbidden()

    subprocess.Popen = ForbiddenProcess
    socket.socket.connect, socket.socket.connect_ex, socket.socket.sendto = scoped_connect, scoped_connect_ex, forbidden
    socket.socketpair = socketpair
    try:
        yield
    finally:
        subprocess.Popen = popen
        socket.socket.connect, socket.socket.connect_ex, socket.socket.sendto = connect, connect_ex, sendto
        socket.socketpair = pair
