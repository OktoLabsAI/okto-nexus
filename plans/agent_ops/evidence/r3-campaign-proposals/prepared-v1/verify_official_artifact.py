"""Pure content checks against current Core; no executable launch or runtime."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parent.parent
CORE = Path('D:/Projetos/Techridy/okto-nexus-connector-core')
sys.path.insert(0, str(CORE / 'src'))
from nexus_connector_core.build_identity import executable_build_identity
from nexus_connector_core.discovery import binary_architecture, fingerprint
from nexus_connector_core.native.adapters.compatibility import qualified_build, CODEX_NATIVE_REQUEST_CONTRACTS

initial = json.loads((ROOT / 'public/codex-0.157.0-artifact-proof.json').read_bytes())
binary = Path(initial['native_executable'])
actual_fingerprint = fingerprint(binary)
actual_identity = executable_build_identity(binary)
architecture = binary_architecture(binary)
source_files = ['src/nexus_connector_core/build_identity.py', 'src/nexus_connector_core/discovery.py', 'src/nexus_connector_core/native/adapters/compatibility.py']
result = {
    'format': 'okto.m1.codex-pure-qualification', 'revision': 1,
    'native_executable': str(binary), 'native_executions': 0,
    'native_version_basis': 'Exact official 0.157.0 release bytes equal the previously qualified executable fingerprint; no version probe was executed.',
    'fingerprint': actual_fingerprint, 'build_identity': actual_identity, 'architecture': architecture,
    'conversation_qualified': qualified_build('codex', '0.157.0', 'win32', architecture, actual_fingerprint, build_identity=actual_identity),
    'controls_qualified': qualified_build('codex', '0.157.0', 'win32', architecture, actual_fingerprint, build_identity=actual_identity, control=True),
    'native_request_contracts': list(CODEX_NATIVE_REQUEST_CONTRACTS['0.157.0']),
    'qualified_route': 'exact executable fingerprint, not the legacy portable identity entry',
    'portable_identity_note': 'Current core.build_identity.v3 identity differs from the retained historical portable grant. Executable fingerprint() is its raw content SHA, as verified in current discovery.py; the generic path-bound docstring does not describe this executable branch.',
    'local_binding_approval': 'still required for the isolated absolute executable and exact project scope',
    'source_files': [{'path': str(CORE / p), 'sha256': hashlib.sha256((CORE / p).read_bytes()).hexdigest()} for p in source_files],
    'provider_authentication_or_config_read': False,
    'effects': {'file_hashing': True, 'binary_execution': False, 'inference': False, 'runtime_started': False},
}
assert result['conversation_qualified'] and result['controls_qualified']
assert result['native_request_contracts'] == ['item/commandExecution/requestApproval']
destination = ROOT / 'public/codex-0.157.0-pure-qualification.json'
with destination.open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'proof': str(destination), 'qualified': True, 'fingerprint': actual_fingerprint, 'native_executions': 0}))
