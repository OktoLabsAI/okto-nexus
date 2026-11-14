from pathlib import Path
import ast,hashlib,json
H=Path(__file__).resolve().parent;R=Path('D:/Projetos/Techridy/okto_labs_okto_nexus');OLD=H.with_name('work-revision15')
C=H/'checks';C.mkdir(exist_ok=True)
initial=['tests/conftest.py','tests/execution_r4/conftest.py','tests/execution_r4/test_native_decision_provenance.py',
 'tests/execution_r4/test_native_decisions.py','tests/execution_r4/test_managed_native_decisions.py']
queue=[R/p for p in initial];seen=set();pins=[]
while queue:
    path=queue.pop()
    if path in seen:continue
    seen.add(path);raw=path.read_bytes();dest=C/path.relative_to(R);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
    pins.append({'path':str(dest),'source':str(path),'sha256':hashlib.sha256(raw).hexdigest()})
    for node in ast.walk(ast.parse(raw)):
        names=[]
        if isinstance(node,ast.ImportFrom) and node.module:names=[node.module.split('.')[0]]
        elif isinstance(node,ast.Import):names=[n.name.split('.')[0] for n in node.names]
        for name in names:
            matches=[p for p in [path.parent/(name+'.py'),R/'tests'/(name+'.py'),R/'tests/execution_r4'/(name+'.py')] if p.is_file()]
            queue.extend(matches[:1])
for name in ['plans/contratos/http-target.schema.json']:
    path=R/name;dest=C/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    pins.append({'path':str(dest),'source':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(C/'fixture-pins.json').write_text(json.dumps({'files':pins},indent=2)+'\n',encoding='utf-8')
s=(OLD/'checks/test_composition.py').read_text(encoding='utf-8')
for a,b in [('revision15','revision16'),("==16","==17"),('295262','341276'),('295287','341301'),
 ("summary['cumulative_reserved_admissions']==12","summary['cumulative_reserved_admissions']==13"),
 ("m1v15-local-useful-13","m1v16-local-useful-14"),("predecessor_connection_generation']==7","predecessor_connection_generation']==8")]:s=s.replace(a,b)
(C/'test_composition.py').write_text(s,encoding='utf-8')
(C/'run_composition.py').write_bytes((OLD/'checks/run_composition.py').read_bytes())
print(json.dumps({'copied_fixture_files':len(pins)}))
