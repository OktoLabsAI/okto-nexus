from pathlib import Path
import hashlib,json,shutil
R=Path('D:/Projetos/Techridy/okto_labs_okto_nexus');P=Path(__file__).parent
(P/'candidate/tests').mkdir(parents=True)
(P/'reports').mkdir()
for name in ['test_serve_lock.py']:
    shutil.copyfile(R/'tests'/name,P/'candidate/tests'/name)
(P/'candidate/pytest.ini').write_text('[pytest]\naddopts = --import-mode=importlib\n',encoding='utf-8')
print('Prepared isolated test copy; no source package copied.')
