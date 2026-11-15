import os
from pathlib import Path
import sys

os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
root = Path('D:/Projetos/Techridy/okto-nexus-connector')
sys.path[:0] = [str(root / 'src'), str(root)]
import pytest

out = Path('C:/Users/jpamb/AppData/Local/Temp/r3-credential-stdin-consent-oq7hnr2y')
raise SystemExit(pytest.main([
    '-p', 'pytest_asyncio.plugin', '-q',
    str(root / 'tests/unit/test_connect_r4.py'),
    str(root / 'tests/unit/test_remote_setup.py') + '::test_continuation_pins_canonical_scope_and_child_ids_before_pipeline',
    str(root / 'tests/unit/test_connect_reuse.py') + '::test_explicit_credential_import_still_validates_and_reactivates_local_identity',
    '--junitxml=' + str(out / 'regressions.xml'),
]))
