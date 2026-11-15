"""Installed constructor only: no HTTP, processes, prepare or provider effects."""
from pathlib import Path
from unittest.mock import patch
import sys,json
H=Path(__file__).parent;sys.path.insert(0,str(H))
from work_context import Context,sha
with patch('subprocess.Popen',side_effect=AssertionError('NO_PROCESS_SELECTED')):
    x=Context(H/'work-plan.json',sha(H/'work-plan.json'))
    assert x.P['project']==str(x.ROOT)
    assert x.P['request_ids']['useful']=='m1-sonnet-remote-useful-07'
    assert not x.PUBLIC.exists() and not x.PRIVATE.exists()
    x.close()
print(json.dumps({'status':'COMPOSED_INSTALLED_CONTEXT_CONSTRUCTOR_PASS','provider_calls':0,'service_effects':0,'http_calls':0,'paid_namespace_created':False}))
