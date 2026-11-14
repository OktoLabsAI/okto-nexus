from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parent
old=Path('C:/Users/jpamb/AppData/Local/Temp/r3-svc-t15-env-zrrzik82/resume02/test_resume02.py')
text=old.read_text(encoding='utf-8');tree=ast.parse(text)
lines=text.splitlines(keepends=True)
node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='test_actual_closed_predecessors_have_no_setup_profile_journal_or_commit')
del lines[node.lineno-1:node.end_lineno]
text=''.join(lines).replace("Path(__file__).with_name('run_case.py')","Path(__file__).with_name('connection_case.py')")
with (ROOT/'test_connection_routes.py').open('x',encoding='utf-8') as f:f.write(text)
with (ROOT/'test-ancestry.json').open('x',encoding='utf-8') as f:json.dump({'path':str(old),
    'sha256':hashlib.sha256(old.read_bytes()).hexdigest(),'delta':'Connection module import only; removed obsolete live predecessor DB test.'},f,indent=2)
