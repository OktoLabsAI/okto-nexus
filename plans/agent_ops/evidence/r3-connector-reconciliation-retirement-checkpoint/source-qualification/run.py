from pathlib import Path
import os,sys,json,hashlib
HERE=Path(__file__).resolve().parent
CORE=Path('D:/Projetos/Techridy/okto-nexus-connector-core')
CONNECTOR=Path('D:/Projetos/Techridy/okto-nexus-connector')
sys.path[:0]=[str(CONNECTOR),str(CORE/'tests')]
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
os.chdir(HERE)
import nexus_connector_core,okto_nexus_connector
assert Path(nexus_connector_core.__file__).is_relative_to(Path(sys.prefix))
assert Path(okto_nexus_connector.__file__).is_relative_to(Path(sys.prefix))
(HERE/'origins.json').write_text(json.dumps({'core':nexus_connector_core.__file__,'connector':okto_nexus_connector.__file__},indent=2)+'\n')
import pytest
raise SystemExit(pytest.main(['-q','-p','pytest_asyncio.plugin','-o','asyncio_mode=auto',
 str(HERE/'test_reproduction.py'),
 str(CORE/'tests/test_cooperative_drain_eviction.py')+'::test_restart_cannot_inherit_process_local_release_proof',
 str(CORE/'tests/test_cooperative_drain_eviction.py')+'::test_eviction_does_not_attest_unjoined_event_producer_or_late_event',
 '--junitxml='+str(HERE/'reproduction.xml')]))
