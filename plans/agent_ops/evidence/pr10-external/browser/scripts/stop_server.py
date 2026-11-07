"""Stop this qualification Server through its current canonical ownership fence."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import socket
import sys
from urllib.parse import urlsplit

sys.path.append('C:/Users/jpamb/AppData/Roaming/Python/Python313/site-packages')
import httpx

ROOT = Path(__file__).resolve().parent / 'qualified'
metadata = json.loads((ROOT / 'server.json').read_text(encoding='utf-8'))
owner = json.loads((ROOT / 'server-owner.json').read_text(encoding='utf-8'))
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel.WaitForSingleObject.restype = wintypes.DWORD
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
handle = kernel.OpenProcess(0x100000, False, owner['server_pid'])
assert handle, 'Could not hold the selected Server process for exit observation'
try:
    with httpx.Client(base_url=metadata['url'], timeout=40, trust_env=False,
                      headers={'Origin': metadata['url'], 'X-Nexus-UI': '1'}) as client:
        response = client.get('/api/v1/service')
        response.raise_for_status()
        current = response.json()['data']
        assert (current['pid'], current['generation'], current['instance_id']) == (
            owner['server_pid'], owner['generation'], owner['instance_id']), 'QA ownership changed'
        stopped = client.post('/api/v1/service/stop', json=dict(instance_id=current['instance_id'],
            generation=current['generation'], timeout_seconds=30.0))
        stopped.raise_for_status()
        result = dict(owner=owner, shutdown=stopped.json())
    result['process_wait_code'] = int(kernel.WaitForSingleObject(handle, 10000))
    assert result['process_wait_code'] == 0, 'Canonical process exit not confirmed'
    target = urlsplit(metadata['url'])
    with socket.socket() as sock:
        sock.settimeout(2)
        result['tcp_connect_code'] = sock.connect_ex((target.hostname, target.port))
    assert result['tcp_connect_code'] != 0, 'Qualification listener still accepts connections'
    (ROOT / 'server-cleanup.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
finally:
    kernel.CloseHandle(handle)
