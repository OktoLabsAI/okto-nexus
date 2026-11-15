from pathlib import Path
import os,sys
ROOT=Path('D:/Projetos/Techridy/okto-nexus-connector')
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT))
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
import pytest
raise SystemExit(pytest.main([str(ROOT/'tests/unit/test_daemon_vault_reload.py'),str(ROOT/'tests/unit/test_vault.py'),'-q','-p','pytest_asyncio.plugin','-p','no:cacheprovider','--junitxml='+str(Path(__file__).parent/'final.xml')]))
