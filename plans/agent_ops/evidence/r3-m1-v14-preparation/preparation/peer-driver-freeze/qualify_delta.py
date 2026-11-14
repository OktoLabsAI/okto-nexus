"""Offline delta only; source v13 unchanged behavior retains prior qualification."""
from pathlib import Path
import os
import sys
import pytest

ROOT=Path(__file__).resolve().parent
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
sys.path.insert(0,str(ROOT))
raise SystemExit(pytest.main(['-q','--tb=short','-p','no:cacheprovider',
    str(ROOT/'test_successor_adoption_authorization.py'),
    str(ROOT/'test_local_only_presence.py'),
    str(ROOT/'test_drivers.py')+'::test_only_frozen_revision_twelve_qualifies_memory_scope',
    str(ROOT/'test_drivers.py')+'::test_predecessor_or_incomplete_approval_refused',
    '--basetemp',str(ROOT/'fixture-run-2'),'--junitxml',str(ROOT/'delta-final.xml')]))
