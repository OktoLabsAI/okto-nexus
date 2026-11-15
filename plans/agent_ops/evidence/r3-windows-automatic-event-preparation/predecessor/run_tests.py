import json
from pathlib import Path
import sys
import unittest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_*.py')
result=unittest.TextTestRunner(verbosity=2).run(suite)
summary={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
         'scope':'Pure command/XML/selection and injected read-only collector fixtures; no OS event/task registration/service/provider'}
(HERE/'test-result.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
raise SystemExit(not result.wasSuccessful())
