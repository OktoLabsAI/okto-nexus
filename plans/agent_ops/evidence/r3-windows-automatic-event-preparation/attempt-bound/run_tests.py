from pathlib import Path
import sys,json,unittest
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(HERE),'test_*.py'))
summary={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
    'scope':'Injected snapshots/handles/dispatch only; no native OS effect, task publication, service or provider'}
with (HERE/'test-result.json').open('x',encoding='utf-8') as f:json.dump(summary,f,indent=2)
raise SystemExit(not result.wasSuccessful())
