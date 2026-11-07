"""Installed CLI entry with read-only command-name audit, no behavior stub."""
import json
import os
from pathlib import Path
import sys

from okto_nexus.adapters.inbound.cli.main import main
from okto_nexus.adapters.outbound.observation.herdr import HerdrCLI
import okto_nexus.application.herdr_observer as application

root = Path(__file__).resolve().parent / 'qualified'
site = Path(sys.prefix) / 'Lib/site-packages'
assert site.resolve() in { (root / 'venv/Lib/site-packages').resolve(),
                          (root.parent / 'qualified-v2/venv/Lib/site-packages').resolve() }
assert Path(application.__file__).resolve().is_relative_to(site)
original = HerdrCLI._run
def audited(self, command, pane_id=None):
    with (root / 'observer-command-audit.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(dict(command=command, pane_id=pane_id)) + '\n')
    return original(self, command, pane_id)
HerdrCLI._run = audited
assert 'PYTHONPATH' not in os.environ
raise SystemExit(main(sys.argv[1:]))
