from pathlib import Path
import sys
import pytest

root = Path(__file__).parent
(root / 'qualification').mkdir(exist_ok=True)
sys.path.insert(0, str(root))
raise SystemExit(pytest.main([str(root / name) for name in sys.argv[1:]] + ['-q', '-p', 'no:cacheprovider',
    '--junitxml=' + str(root/'qualification/final.xml'), '--basetemp=' + str(root/'fixture-temp')]))
