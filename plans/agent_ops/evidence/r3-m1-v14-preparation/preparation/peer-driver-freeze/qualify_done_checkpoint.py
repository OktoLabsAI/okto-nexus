"""Focused installed CLI check: previous authorization done permits fresh review."""
from pathlib import Path
import os
import sys
import pytest
ROOT=Path(__file__).resolve().parent
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
sys.path.insert(0,str(ROOT))
raise SystemExit(pytest.main(['-q','--tb=short','-p','no:cacheprovider',
    str(ROOT/'test_successor_adoption_authorization.py')+'::test_installed_parser_and_handlers_review_then_single_cas_issue[True]',
    '--basetemp',str(ROOT/'fixture-done-checkpoint'),'--junitxml',str(ROOT/'delta-done-checkpoint.xml')]))
