"""Installed CLI with empty synthetic discovery and disposable application data."""
import importlib.metadata
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent / 'qualified'
SERVER_HOME = ROOT / 'server-home'
SITE = ROOT / 'venv/Lib/site-packages'
REPO = Path(sys.argv[1]).resolve()
port = sys.argv[2]
dependency_site = Path(sys.argv[3]).resolve()
sys.dont_write_bytecode = True
sys.path[:] = [p for p in sys.path if p and not Path(p).resolve().is_relative_to(REPO.parent)]
sys.path.append(str(dependency_site))
os.chdir(SERVER_HOME)
import okto_nexus
import nexus_connector_core
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.bootstrap import embedded_inventory
from okto_nexus.adapters.inbound.cli.main import main

embedded_inventory.discover_local_candidates = lambda **_: SimpleNamespace(candidates=())
args = ['--home', str(SERVER_HOME), '--embedding-mode', 'off', '--feature-harness-integrations', 'false',
        '--feature-memory', 'false', '--metrics-mode', 'disabled']
deps = bootstrap({}, args)
with deps.connection_factory.unit_of_work() as uow:
    for workspace in ('pr10-workspace-a', 'pr10-workspace-b'):
        deps.repos.workspaces.upsert(uow, workspace_id=workspace)
deps.connection_factory.close()
paths = {name: str(Path(module.__file__).resolve()) for name, module in list(sys.modules.items())
         if (name == 'okto_nexus' or name.startswith('okto_nexus.') or name == 'nexus_connector_core'
             or name.startswith('nexus_connector_core.')) and getattr(module, '__file__', None)}
assert all(Path(path).is_relative_to(SITE) for path in paths.values())
(ROOT / 'server-import-proof.json').write_text(json.dumps(dict(
    python=sys.executable, nexus_version=importlib.metadata.version('okto-nexus'),
    core_version=importlib.metadata.version('okto-nexus-connector-core'), shared_dependency_site=str(dependency_site),
    modules=paths, discovery='synthetic empty; no real provider/client discovery', home=str(SERVER_HOME),
    embedding_mode='off', metrics_mode='disabled', feature_memory=False,
    feature_harness_integrations=False, observation_feature_at_start='default false, not pinned'), indent=2), encoding='utf-8')
raise SystemExit(main(['serve', '--host', '127.0.0.1', '--port', port, '--log-level', 'warning', *args]))
