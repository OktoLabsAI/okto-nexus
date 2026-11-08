"""Final touched installer and entry denial gates; no product imports/effects."""
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).parent
assert Path(sys.prefix) == ROOT / 'installation/venv'
sys.path.insert(0,str(ROOT))
sys.argv = [str(ROOT / 'test_entry_guards.py')]
runpy.run_path(str(ROOT / 'test_entry_guards.py'),run_name='__main__')
import pytest
raise SystemExit(pytest.main([str(ROOT/'installation/test_timed_install.py'),
    '-q','-p','no:cacheprovider','--basetemp',str(ROOT/'final-synthetic-test-homes'),
    '--junitxml',str(ROOT/'final-gates.xml')]))
