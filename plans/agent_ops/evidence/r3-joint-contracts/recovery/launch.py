from pathlib import Path
import json,subprocess,sys
p=Path(__file__).parent
cmd=[sys.executable,str(p/'run_redacted.py'),'ci-runner','rtk','proxy',r'C:/Users/jpamb/AppData/Local/Temp/nexus-ci-connector-refresh-la1tb1l6/venv/Scripts/python.exe','-X','utf8',r'D:/Projetos/Techridy/okto_labs_okto_nexus/tools/ci_installed.py','test','--wheel',r'C:/Users/jpamb/AppData/Local/Temp/dx04-mcp-guide-installed-sk13m28a/candidate-v1/wheels/okto_nexus-0.3.3-py3-none-any.whl','--output',str(p/'ci'),'--tests',*json.loads((p/'selection.json').read_text())]
raise SystemExit(subprocess.call(cmd))
