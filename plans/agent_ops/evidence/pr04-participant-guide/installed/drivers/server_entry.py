"""Real installed CLI; explicit isolated synthetic seed, no discovery/provider."""
import importlib.metadata
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

candidate = Path(sys.argv[1]).resolve()
scenario, port = sys.argv[2:4]
dependency_site = Path(sys.argv[4]).resolve()
proof = json.loads((candidate / 'package-proof.json').read_text())
repo = Path(proof['source_root']).resolve()
scenario_root = candidate / 'servers' / scenario
task_home = scenario_root / 'home'
site = candidate / 'venv/Lib/site-packages'
assert scenario in ('onboarding', 'agents')
sys.dont_write_bytecode = True
sys.path[:] = [p for p in sys.path if p and not Path(p).resolve().is_relative_to(repo.parent)]
sys.path.append(str(dependency_site))
os.chdir(task_home)

import okto_nexus
import nexus_connector_core
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.bootstrap import embedded_inventory
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.application.agent_creation import create_agent_in_uow
from okto_nexus.adapters.inbound.http.app import ensure_operator_key
from okto_nexus.adapters.inbound.cli.main import main

embedded_inventory.discover_local_candidates = lambda **_: SimpleNamespace(candidates=())
args = ['--home', str(task_home), '--embedding-mode', 'off', '--feature-harness-integrations', 'false']
deps = bootstrap({}, args)
auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
# Canonical cold-start credential exists but plaintext never leaves memory.
# Discard it before the foreground CLI begins; nothing prints or stores it.
material = ensure_operator_key(deps, auth)
del material
if scenario == 'agents':
    with deps.connection_factory.unit_of_work() as uow:
        for suffix in ('alpha', 'beta'):
            project = scenario_root / ('project-' + suffix)
            project.mkdir()
            deps.repos.workspaces.upsert(uow, workspace_id='dx04-workspace-' + suffix,
                display_name='DX04 synthetic ' + suffix, root_realpath=str(project))
            agent, material = create_agent_in_uow(deps, uow, auth,
                agent_id='dx04-agent-' + suffix, role='reviewer', metadata={'qualification': 'synthetic DX04 guide'})
            del material, agent
deps.connection_factory.close()
modules = {name: str(Path(module.__file__).resolve()) for name, module in list(sys.modules.items())
    if (name == 'okto_nexus' or name.startswith('okto_nexus.') or name == 'nexus_connector_core'
        or name.startswith('nexus_connector_core.')) and getattr(module, '__file__', None)}
assert all(Path(path).is_relative_to(site) for path in modules.values()), 'Editable import leakage.'
assert importlib.metadata.version('okto-nexus') == proof['version']
assert importlib.metadata.version('okto-nexus-connector-core') == '0.0.14'
with (scenario_root / 'import-proof.json').open('x', encoding='utf-8') as output:
    json.dump(dict(pid=os.getpid(), python=sys.executable, python_version=sys.version,
        nexus_version=importlib.metadata.version('okto-nexus'),
        core_version=importlib.metadata.version('okto-nexus-connector-core'), modules=modules,
        dependencies={name: importlib.metadata.version(name) for name in ('mcp', 'fastapi', 'uvicorn', 'pydantic')},
        shared_dependency_site=str(dependency_site), scenario=scenario, home=str(task_home),
        discovery='synthetic empty', native_providers_started=False, one_shot_material_recorded=False,
        seed='reserved operator only' if scenario == 'onboarding' else 'reserved operator + 2 synthetic identities/workspaces',
        feature_harness_integrations=False, embedding_mode='off'), output, indent=2)
raise SystemExit(main(['serve', '--host', '127.0.0.1', '--port', port, '--log-level', 'warning', *args]))
