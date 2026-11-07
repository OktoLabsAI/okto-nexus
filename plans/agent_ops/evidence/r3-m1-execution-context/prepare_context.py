"""Prepare exact M1 references; no registration, start, provider or secret reads."""
from pathlib import Path
import hashlib
import json
import socket
import sys
import tempfile
import zipfile

repo = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
proposal_path = repo / 'plans/agent_ops/evidence/r3-m1-budget-update/m1-codex-campaign-proposal-v4.json'
proposal = json.loads(proposal_path.read_text(encoding='utf-8'))
root = Path(tempfile.mkdtemp(prefix='m1-context-preparation-'))
prefix = Path(sys.prefix).resolve()
assert sys.flags.isolated
import okto_nexus
import okto_nexus_connector
import nexus_connector_core
from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation
from okto_nexus_connector.platform.user_service import UserService

proof = {}
for key, module in [('nexus', okto_nexus), ('connector', okto_nexus_connector), ('core', nexus_connector_core)]:
    package = Path(module.__file__).resolve().parent
    assert package.is_relative_to(prefix)
    pin = proposal['package_pins'][key]
    wheel = Path(pin['wheel'])
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == pin['wheel_sha256']
    with zipfile.ZipFile(wheel) as archive:
        expected = {name.split('/', 1)[1]: hashlib.sha256(archive.read(name)).hexdigest()
                    for name in archive.namelist() if name.startswith(module.__name__ + '/') and not name.endswith('/')}
    actual = {p.relative_to(package).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in package.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}
    assert actual == expected
    proof[key] = dict(import_path=str(package), wheel_sha256=pin['wheel_sha256'], exact_payload_files=len(expected))

home = Path(proposal['paths']['server_home'])
state = Path(proposal['paths']['connector_state'])
selected = [('nexus', ServerInstallation(home, home / 'nexus.db')), ('connector', UserService(state))]
tasks = {}
for name, installation in selected:
    # Exact read only. No registration/validation/start/enable/delete API.
    observed = installation.tasks.read(installation.name)
    tasks[name] = dict(name=installation.name, instance_id=installation.instance_id, exists=observed is not None)
    assert observed is None
paths = {key: dict(path=value, exists=Path(value).exists())
         for key, value in proposal['paths'].items() if key != 'codex_executable'}
assert not any(row['exists'] for row in paths.values()), 'M1 paths already exist; inspect without overwriting.'
with socket.socket() as probe:
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
native = Path(proposal['paths']['codex_executable'])
assert hashlib.sha256(native.read_bytes()).hexdigest() == proposal['native_selection']['fingerprint'].split(':', 1)[1]
report = dict(status='READ_ONLY_PREPARATION', proposal_sha256=hashlib.sha256(proposal_path.read_bytes()).hexdigest(),
    installed_packages=proof, tasks=tasks, proposed_paths=paths, origin=f'http://127.0.0.1:{port}',
    port_available_at_preparation=True, port_recheck_required=True,
    provider_home_candidate='C:/Users/jpamb/.codex',
    provider_home_basis='Parent task observed CODEX_HOME unset; default user-home/.codex. No contents opened.',
    native_sha256=hashlib.sha256(native.read_bytes()).hexdigest(),
    native_commands_executed=[], credentials_read=False, service_mutations=False,
    limits=['Native provider use and service lifecycle remain unauthorized.',
            'Exact absence and port availability are point-in-time observations, not reservations.',
            'Provider home path alone does not prove login, effective policy or credential access from a service.'])
(root / 'context.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(output=str(root / 'context.json'), tasks=tasks, origin=report['origin'])))
