"""Offline plan construction; no native tasks, sockets, runtimes or state stores."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parent
B = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7')
p = json.loads((B / 'draft/m1-codex-campaign-proposal-v12.json').read_bytes())
assert Path(sys.executable).resolve() == Path(p['package_pins']['python']).resolve()
from okto_nexus.adapters.outbound.service_manager.identity import server_instance_id
from okto_nexus_connector.platform.service_identity import service_instance_id

python = str(Path(sys.executable).resolve())
project, caller = str(ROOT / 'project-a'), str(ROOT / 'caller-b')
homes = {'nexus': str(ROOT / 'nexus'), 'connector': str(ROOT / 'connector')}
instance = {'nexus': server_instance_id(Path(homes['nexus']), Path(homes['nexus']) / 'nexus.db'),
            'connector': service_instance_id(Path(homes['connector']))}
env = {'COMSPEC': 'C:/WINDOWS/System32/cmd.exe', 'PATHEXT': '.COM;.EXE;.BAT;.CMD',
    'SYSTEMROOT': 'C:/WINDOWS', 'WINDIR': 'C:/WINDOWS', 'PYTHONDONTWRITEBYTECODE': '1',
    'PYTHONUNBUFFERED': '1', 'OKTO_NEXUS_NO_BANNER': '1', 'OKTO_NEXUS_CONNECTOR_VAULT': 'file',
    'USERPROFILE': str(ROOT / 'profile'), 'APPDATA': str(ROOT / 'profile/appdata'),
    'LOCALAPPDATA': str(ROOT / 'profile/localappdata'), 'TEMP': str(ROOT / 'profile/tmp'),
    'TMP': str(ROOT / 'profile/tmp'),
    'PATH': str(Path(python).parent) + ';C:/Python313;C:/WINDOWS/System32'}
base = [python, '-I', '-B', '-m']
nx = base + ['okto_nexus.adapters.inbound.cli.main']
cn = base + ['okto_nexus_connector.cli.main', '--state-dir', homes['connector'], '--non-interactive', '--json']
port = 58843
nx_config = ['--home', homes['nexus'], '--host', '127.0.0.1', '--port', str(port),
    '--project-root', project, '--embedding-mode', 'off', '--feature-harness-integrations', 'false', '--metrics-mode', 'disabled']
commands = {'nexus': {}, 'connector': {}}
def step(name, phase, argv, source='B'):
    commands[name][phase] = {'argv': argv, 'environment': source, 'cwd': project if source == 'A' else caller}
step('nexus', 'install-A', nx + ['service', 'install', '--user', '--start-at-login', '--json', *nx_config], 'A')
step('nexus', 'start-B', nx + ['service', 'start', '--home', homes['nexus'], '--timeout', '45', '--json'])
for phase in ('stop-installed', 'stop-foreground'):
    step('nexus', phase, nx + ['service', 'stop', '--home', homes['nexus'], '--timeout', '45', '--json'])
step('nexus', 'uninstall', nx + ['service', 'uninstall', '--user', '--home', homes['nexus'], '--json'])
step('nexus', 'foreground', nx + ['serve', *nx_config])
step('connector', 'install-A', cn + ['service', 'install'], 'A')
step('connector', 'start-B', cn + ['daemon', 'start', '--timeout', '45'])
for phase in ('stop-installed', 'stop-foreground'):
    step('connector', phase, cn + ['daemon', 'stop', '--timeout', '45'])
step('connector', 'uninstall', cn + ['service', 'uninstall'])
step('connector', 'foreground', cn + ['daemon', 'run'])
images = {Path(python), Path(python).with_name('pythonw.exe'), Path(sys._base_executable), Path(sys._base_executable).with_name('pythonw.exe')}
plan = {'format': 'okto.r3.t14-t27.finite', 'revision': 1, 'status': 'OFFLINE_PREPARED_NOT_EXECUTED',
    'root': str(ROOT), 'python': python, 'homes': homes, 'project_a': project, 'caller_b': caller, 'port': port,
    'instance_ids': instance, 'tasks': {name: 'OktoNexus-' + ('server' if name == 'nexus' else 'connector') + '-' + value[4:] for name, value in instance.items()},
    'environments': {'A': env, 'B': {**env, 'PATH': 'C:/WINDOWS/System32'}}, 'commands': commands,
    'python_images': {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(images)},
    'observation_timeout_seconds': 180, 'canonical_stop_timeout_seconds': 45,
    'uninstall_removes': {'nexus': ['service-installation.json', 'service-control.json', 'nexus.db.service-installation.json'],
                          'connector': ['service-installation.json', 'service-control.json']},
    'actions': {'canonical_cli_selections': 12, 'scheduled_service_starts': 2, 'foreground_starts': 2, 'normal_stops': 4,
                'uninstalls': 2, 'native_manual_edits': 0, 'provider_calls': 0, 'login_attempts': 0, 'force': False},
    'limits': ['Readiness polling only; start/stop selections are exclusive and never automatically repeated.',
        'Connector T14 is scoped to its canonical state root, not a project binding or productive remote work.',
        'T27 requires runtime-created DBs and byte preservation across uninstall; foreground may legitimately change DB bytes.',
        'No M1 files/services/accounts modified. Root executes after M1 preparation.']}
(ROOT / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'plan_sha256': hashlib.sha256((ROOT / 'plan.json').read_bytes()).hexdigest(), 'tasks': plan['tasks'], 'port': port}))
