from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent
repo = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
sys.path[:0] = [str(repo/'src'), str(repo/'tests'), str(repo/'tests/execution_r4')]
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
import pytest

files = sys.argv[1:] or ['test_native_decision_provenance.py']
raise SystemExit(pytest.main([*[str(repo/'tests/execution_r4'/f) for f in files],
    '-q', '--junitxml='+str(ROOT/('final.xml' if len(files)>1 else 'focal.xml'))]))
