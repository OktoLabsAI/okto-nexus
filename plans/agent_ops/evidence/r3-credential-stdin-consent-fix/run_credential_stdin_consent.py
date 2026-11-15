import os
from pathlib import Path
import sys
import tempfile

os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
root = Path('D:/Projetos/Techridy/okto-nexus-connector')
sys.path[:0] = [str(root / 'src'), str(root)]
import pytest
import okto_nexus_connector

evidence = Path(tempfile.mkdtemp(prefix='r3-credential-stdin-consent-'))
print('EVIDENCE', evidence, flush=True)
print('SOURCE', okto_nexus_connector.__file__, flush=True)
raise SystemExit(pytest.main([
    '-p', 'pytest_asyncio.plugin', '-q',
    str(root / 'tests/unit/test_credential_stdin_consent.py'),
    '--junitxml=' + str(evidence / 'focused.xml'),
]))
