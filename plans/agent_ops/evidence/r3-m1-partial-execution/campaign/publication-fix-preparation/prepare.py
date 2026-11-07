from pathlib import Path
import ast,hashlib,json
root=Path(__file__).parent
original=(root/'original_m1_real_work.py').read_text()
assert hashlib.sha256((root/'original_m1_real_work.py').read_bytes()).hexdigest()=='c0903937d3ce737764200ebcaa6ab9d1f6ec364b03a68c1d2ce51a2a6bd9a1f3'
source=original.replace("sys.path.insert(0,'C:/Users/jpamb/AppData/Local/Temp')", "sys.path.insert(0,str(Path(__file__).parent))\nfrom publication import poll_and_publish\nsys.path.insert(0,'C:/Users/jpamb/AppData/Local/Temp')",1)
source=source.replace("recovered_decisions={}","recovered_decisions={}\npublication_diagnostics={}",1)
before="        summary=controller.poll()\n        public_write('live-accounting.json',{'time':time.time(),'summary':summary,'active_request':request})"
after="        summary=poll_and_publish(controller,lambda value:public_write('live-accounting.json',value),publication_diagnostics,request)"
assert before in source
source=source.replace(before,after,1)
source=source.replace("'decision_count':len(selected_decisions)","'publication_diagnostics':publication_diagnostics,'decision_count':len(selected_decisions)",1)
source=source.replace("'containment_error_type':containment_error", "'publication_diagnostics':publication_diagnostics,'containment_error_type':containment_error",1)
source=source.replace("str(Path(__file__).with_name('m1_real_lifecycle.py'))", "str(Path('C:/Users/jpamb/AppData/Local/Temp/m1_real_lifecycle.py'))")
ast.parse(source)
(root/'prepared_m1_real_work.py').write_text(source)
print(json.dumps({'original_sha256':hashlib.sha256((root/'original_m1_real_work.py').read_bytes()).hexdigest(),
                  'prepared_sha256':hashlib.sha256((root/'prepared_m1_real_work.py').read_bytes()).hexdigest(),
                  'provider_execution':False}))
