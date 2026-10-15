"""Real pipe byte fragmentation and concurrent stdout/stderr pressure."""
import json
from pathlib import Path
import sys

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_commands import wait_operation

runtime = runtime_fixture

WIRE = r'''
import os,threading,time
from pathlib import Path
_pressure_started=False
_stats={'fragmented_frames':0,'stdout_bytes':0,'stderr_bytes':0}
def _write_all(fd,data):
    while data:
        count=os.write(fd,data)
        data=data[count:]
def wire_write(text):
    global _pressure_started
    encoded=text.encode('utf-8')
    marker='🧪'.encode('utf-8')
    at=encoded.find(marker)
    flood=None
    if at>=0:
        # Legal JSON whitespace makes a frame larger than ordinary pipe
        # capacity while staying below the unchanged parser frame limit.
        encoded=encoded.rstrip(b'\n')+b' '*131072+b'\n'
        if not _pressure_started:
            _pressure_started=True
            def stderr_flood():
                data=b'e'*4096
                for _ in range(512):
                    _write_all(2,data)
                    _stats['stderr_bytes']+=len(data)
            flood=threading.Thread(target=stderr_flood)
            flood.start()
        _write_all(1,encoded[:at+1])
        for byte in encoded[at+1:at+4]:
            time.sleep(.002)
            _write_all(1,bytes([byte]))
        _write_all(1,encoded[at+4:])
        _stats['fragmented_frames']+=1
    else:
        _write_all(1,encoded)
    _stats['stdout_bytes']+=len(encoded)
    if flood:
        flood.join(10)
        assert not flood.is_alive(), 'stderr not drained'
    Path(STATS_PATH).write_text(json.dumps(_stats))
'''
