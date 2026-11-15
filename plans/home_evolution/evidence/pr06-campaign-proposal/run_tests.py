from pathlib import Path
import hashlib
import json
import sys
import time
import unittest
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).parent))
import test_driver
root=Path(__file__).parent
suite=unittest.defaultTestLoader.loadTestsFromModule(test_driver)
started=time.monotonic()
result=unittest.TextTestRunner(verbosity=1).run(suite)
elapsed=time.monotonic()-started
xml=ET.Element('testsuite',name='home033-offline-driver',tests=str(result.testsRun),
    failures=str(len(result.failures)),errors=str(len(result.errors)),skipped=str(len(result.skipped)),time=str(elapsed))
for test,trace in result.failures+result.errors:
    ET.SubElement(ET.SubElement(xml,'testcase',name=test.id()),'failure').text=trace
ET.ElementTree(xml).write(root/'final.xml',encoding='utf-8',xml_declaration=True)
from okto_nexus.adapters.inbound.cli import work,service,connect
origins=[]
for module in (work,service,connect):
    path=Path(module.__file__).resolve()
    origins.append({'module':module.__name__,'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(root/'parser-origins.json').write_text(json.dumps({'python':sys.executable,'prefix':sys.prefix,'origins':origins},indent=2)+'\n')
(root/'test-result.json').write_text(json.dumps({'passed':result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped),
    'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
    'elapsed_seconds':elapsed,'installed_product_boundary_mocked':True,'provider_calls':0,'service_actions':0,
    'source_path_injection_for_product':False},indent=2)+'\n')
raise SystemExit(not result.wasSuccessful())
