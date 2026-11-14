import hashlib
import json
import os
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
SITE = BASE / 'installed-product'
os.environ['HOME'] = str(BASE / 'runner-home')
os.environ['USERPROFILE'] = str(BASE / 'runner-home')
os.environ['OKTO_NEXUS_HOME'] = str(BASE / 'runner-home' / 'nexus')
os.environ['CODEX_HOME'] = str(BASE / 'runner-home' / '.codex')
os.environ.pop('PYTHONPATH', None)
sys.path.insert(0, str(BASE / 'installed-tests'))
sys.path.insert(0, str(SITE))
import okto_nexus
import nexus_connector_core
from okto_nexus.adapters.inbound.cli import work
assert Path(okto_nexus.__file__).resolve().is_relative_to(SITE)
assert Path(work.__file__).resolve().is_relative_to(SITE)
assert 'dx-t34-nexus-qualification-i2obuu_g' in nexus_connector_core.__file__
imports = dict(python=sys.executable, isolated=sys.flags.isolated, pythonpath=os.environ.get('PYTHONPATH'),
    nexus=okto_nexus.__file__, core=nexus_connector_core.__file__, cli_work=work.__file__,
    cli_work_sha256=hashlib.sha256(Path(work.__file__).read_bytes()).hexdigest())
(BASE / 'installed-imports.json').write_text(json.dumps(imports, indent=2), encoding='utf8')
import pytest
raise SystemExit(pytest.main(['-c', str(BASE / 'pytest-installed.ini'),
    str(BASE / 'installed-tests' / 'execution_r4' / 'test_terminal_work.py'),
    '-k', 'cli_drain', '-q', '--tb=short', '--junitxml=' + str(BASE / 'installed.xml')]))
