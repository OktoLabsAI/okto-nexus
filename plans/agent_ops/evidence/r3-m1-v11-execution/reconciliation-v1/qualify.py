"""Run offline synthetic fixtures; does not invoke reconciliation main/gate."""
from pathlib import Path
import os
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
import pytest

if __name__ == '__main__':
    raise SystemExit(pytest.main([str(HERE / 'test_reconcile_presence.py'), '-q', '-p',
                                 'no:cacheprovider', '--junitxml=' + str(HERE / 'results.xml')]))
