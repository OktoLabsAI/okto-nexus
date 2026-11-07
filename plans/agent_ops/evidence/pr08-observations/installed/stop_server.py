"""Canonical shutdown of this isolated server, guarded by current owner facts."""
import json
from pathlib import Path
import httpx

metadata = json.loads((Path(__file__).resolve().parent / 'qualified/server.json').read_text())
owner = json.loads((Path(__file__).resolve().parent / 'qualified/server-owner.json').read_text())
with httpx.Client(base_url=metadata['url'], timeout=40,
                  headers={'Origin': metadata['url'], 'X-Nexus-UI': '1'}) as client:
    response = client.get('/api/v1/service')
    response.raise_for_status()
    current = response.json()['data']
    assert (current['pid'], current['generation'], current['instance_id']) == (
        owner['server_pid'], owner['generation'], owner['instance_id']), 'The listening server is no longer this isolated QA owner.'
    stopped = client.post('/api/v1/service/stop', json={
        'instance_id': current['instance_id'], 'generation': current['generation'], 'timeout_seconds': 30.0})
    stopped.raise_for_status()
    print(json.dumps(stopped.json()))
