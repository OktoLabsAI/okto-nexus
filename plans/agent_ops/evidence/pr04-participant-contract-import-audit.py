import _thread
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
allowed = [Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()]
events = []
def audit(event, args):
    if event in ('socket.__new__', 'socket.connect', 'subprocess.Popen', 'os.system', 'os.fork', 'os.posix_spawn'):
        raise RuntimeError('Unexpected import effect: ' + event)
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).resolve()
        if not any(path.is_relative_to(parent) for parent in allowed):
            raise RuntimeError('Unexpected non-code file read during import')
        events.append('code_read')
def no_thread(*_args, **_kwargs):
    raise RuntimeError('Unexpected thread during import')
_thread.start_new_thread = no_thread
sys.addaudithook(audit)
import nexus_connector_core.participant_config as participant
value = participant.participant_client_config(client='generic', client_version=None,
    server_url='https://nexus.example/mcp', approved_origin='https://nexus.example',
    entry_name='nexus-audit', credential_environment='NEXUS_PARTICIPANT_TOKEN_AUDIT', file_scope='manual')
participant.export_participant_config(value)
assert participant.__file__.startswith(sys.prefix)
print(json.dumps(dict(module=participant.__file__, import_and_render='PASS',
    network_process_thread_effects=0, non_code_file_reads=0, code_reads=len(events))))
