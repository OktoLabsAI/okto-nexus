"""Loopback-only IPC hint. A datagram conveys no identity or work authority."""
import json
import os
from pathlib import Path
import socket
import threading

_FILENAME = "runtime-wake.json"


class RuntimeWakeChannel:
    def __init__(self, home_dir, api_url=None):
        self.home = Path(home_dir)
        self.api_url = api_url
        self._stop = threading.Event()
        self._socket = None

    def start(self, wake, owner_id):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        sock.settimeout(1)
        self._socket = sock
        self._stop.clear()
        record = {"version": 1, "host": "127.0.0.1", "port": sock.getsockname()[1], "owner_id": owner_id}
        if self.api_url:
            record["api_url"] = self.api_url
        temporary = self.home / (_FILENAME + "." + owner_id)
        with open(temporary, "x", encoding="utf-8") as stream:
            os.chmod(temporary, 0o600)
            json.dump(record, stream)
        os.replace(temporary, self.home / _FILENAME)

        def receive():
            while not self._stop.is_set():
                try:
                    packet, source = sock.recvfrom(128)
                    if source[0] == "127.0.0.1" and packet == owner_id.encode():
                        wake()  # Coalesced Event; payload can never name work.
                except socket.timeout:
                    continue
                except OSError:
                    break

        self._thread = threading.Thread(target=receive, daemon=True, name="nexus-runtime-wake")
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._socket:
            self._socket.close()
            self._thread.join(2)
        # Keep a stale hint rather than risk deleting a successor's record.
        # A failed/lost hint is recovered by the owner's indexed timer.


def signal_runtime_owner(home_dir):
    try:
        path = Path(home_dir) / _FILENAME
        if path.stat().st_size > 1024:
            return False
        record = json.loads(path.read_text(encoding="utf-8"))
        if (record.get("version") != 1 or record.get("host") != "127.0.0.1" or
                type(record.get("port")) is not int or not 0 < record["port"] < 65536 or
                not isinstance(record.get("owner_id"), str) or len(record["owner_id"]) > 100):
            return False
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(record["owner_id"].encode(), ("127.0.0.1", record["port"]))
        return True
    except (OSError, ValueError, TypeError):
        return False
