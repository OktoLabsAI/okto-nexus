"""Serialize exact proposed commands; never execute them."""
from pathlib import Path
import json
import shutil

root = Path('C:/Users/jpamb/AppData/Local/Temp/m1-context-preparation-v0u6i9vu')
context = json.loads((root / 'context.json').read_text())
discovery = json.loads(Path('C:/Users/jpamb/AppData/Local/Temp/m1-native-discovery-iyoo0rs3/discovery.json').read_text())
proposal = json.loads(Path('D:/Projetos/Techridy/okto_labs_okto_nexus/plans/agent_ops/evidence/r3-m1-budget-update/m1-codex-campaign-proposal-v4.json').read_text(encoding='utf-8'))
paths = proposal['paths']
python = proposal['package_pins']['nexus']['python_path']
origin = context['origin']
port = origin.rsplit(':', 1)[1]
service_selection = ['--home', paths['server_home'], '--host', '127.0.0.1', '--port', port,
    '--project-root', paths['local_project'], '--embedding-mode', 'off',
    '--feature-harness-integrations', 'true', '--metrics-mode', 'disabled',
    '--harness-root', discovery['package_root']]
nexus = [python, '-I', '-B', '-m', 'okto_nexus.adapters.inbound.cli.main']
connector = [python, '-I', '-B', '-m', 'okto_nexus_connector.cli.main', '--state-dir', paths['connector_state'], '--non-interactive']
steps = []
for component in ('nexus', 'connector'):
    for action in ('install', 'start', 'stop', 'uninstall'):
        if component == 'nexus':
            consent = ['--user', '--start-at-login'] if action == 'install' else ['--user'] if action == 'uninstall' else []
            argv = [*nexus, 'service', action, *consent, *service_selection, '--timeout', '45', '--json']
        else:
            family = 'service' if action in ('install', 'uninstall') else 'daemon'
            duration = ['--timeout', '45'] if action in ('start', 'stop') else []
            argv = [*connector, family, action, *duration, '--json']
        steps.append(dict(component=component, action=action, task_name=context['tasks'][component]['name'], argv=argv))
result = dict(status='PROPOSED_NOT_EXECUTED', native=discovery['candidate']['executable'],
    candidate_ref=discovery['candidate']['installation_ref'], provider_home=context['provider_home_candidate'],
    origin=origin, tasks=context['tasks'], steps=steps, service_selection_args=service_selection,
    required_parent_path=[discovery['package_root'], 'C:/Windows/System32', 'C:/Program Files/Git/cmd'],
    environment_scope='Use a dedicated bootstrap environment with this PATH; do not inherit provider keys or personal CLI settings into service definitions.',
    phases=['Install/start Nexus before local connect.', 'Install/start Connector before remote connect.',
            'After both finite work lanes are terminal, stop/drain and uninstall each owned task.'],
    guards=['Recheck pinned artifacts, exact task absence, empty homes and port before effects.',
            'Create only the reviewed scratch paths/fixture files before install; never overwrite existing paths.',
            'Registration generates ownership tokens privately; never export raw task XML or token-bearing argv.',
            'No restart, force, logout or reboot is included here. Unconfirmed stop/cleanup is reported, not bypassed.',
            'The separate 24-action empty-service proposal uses different homes and two other task names.'],
    counts=dict(m1_service_mutations=8, m1_user_tasks=2, provider_admissions_max=6,
                separate_empty_service_mutations=24, separate_empty_service_user_tasks=2),
    commands_executed=0, authorization_received=False)
(root / 'proposed-commands.json').write_text(json.dumps(result, indent=2) + '\n')
shutil.copy2('C:/Users/jpamb/AppData/Local/Temp/prepare_m1_context.py', root / 'prepare_context.py')
shutil.copy2('C:/Users/jpamb/AppData/Local/Temp/prepare_m1_discovery.py', root / 'prepare_discovery.py')
shutil.copy2(__file__, root / 'prepare_commands.py')
shutil.copy2('C:/Users/jpamb/AppData/Local/Temp/m1-native-discovery-iyoo0rs3/discovery.json', root / 'discovery.json')
print(json.dumps(dict(output=str(root / 'proposed-commands.json'), mutation_count=len(steps), executed=0)))
