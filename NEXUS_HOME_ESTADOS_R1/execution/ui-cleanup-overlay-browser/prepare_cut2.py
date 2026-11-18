"""Static cut2 rebind; original Cp1 scripts/cut remain unchanged."""
import ast,hashlib,json,difflib
from pathlib import Path
HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
text=(HERE/'run.py').read_text().replace("js=='/assets/index-Cp1x7DiS.js'","js=='/assets/index-8qNwMfLq.js'")
old="assert all(sha(REPO/p)==h for p,h in backend.items())"
new="""exception='src/okto_nexus/adapters/outbound/sqlite/home.py';exception_sha='50835c0a009ba5b1d67dac8a01827aae57424c49d8812b2e6a3d1da287e42d25';assert sha(REPO/exception)==exception_sha
 assert all(sha(REPO/p)==h for p,h in backend.items()if p!=exception)"""
assert text.count(old)==1;text=text.replace(old,new)
text=text.replace("dict(wheel=ready['wheel_sha256'],payload1031=True,backend_count=", "dict(wheel=ready['wheel_sha256'],payload1031=True,checkout_exception=dict(path=exception,sha256=exception_sha,runtime_uses_original_installed_home_py=True),backend_count=")
text=text.replace("HERE/'pins-before.json'","HERE/'pins-before-cut2.json'").replace("HERE/'runtime.json'","HERE/'runtime-cut2.json'").replace("--session=hst-overlay-cp1","--session=hst-overlay-8qn").replace("HERE/'browser.js'","HERE/'browser-cut2.js'")
ast.parse(text);(HERE/'run_cut2.py').write_text(text)
js=(HERE/'browser.js').read_text().replace('index-Cp1x7DiS.js','index-8qNwMfLq.js').replace("data.lifecycle_state==='READY'","['READY','ACTIVE'].includes(data.lifecycle_state)")
(HERE/'browser-cut2.js').write_text(js)
diff=''.join(difflib.unified_diff((HERE/'run.py').read_text().splitlines(True),text.splitlines(True),fromfile='run.py',tofile='run_cut2.py'))+''.join(difflib.unified_diff((HERE/'browser.js').read_text().splitlines(True),js.splitlines(True),fromfile='browser.js',tofile='browser-cut2.js'))
(HERE/'cut2.diff').write_text(diff)
(HERE/'cut2-prepared.json').write_text(json.dumps(dict(layer='Real Chrome + unchanged installed R9 HTTP API + Vite index-8qNwMfLq static-only overlay; not new installed wheel',exception='Checkout SQLite home.py SHA50835c0a009ba5b1d67dac8a01827aae57424c49d8812b2e6a3d1da287e42d25 only; runtime stays old package',cut1_observed_lifecycle_states=['READY'],checks_condition='READY or ACTIVE + control_available true + no durable release pending, as current UI contract',files={n:sha(HERE/n)for n in ['run_cut2.py','browser-cut2.js','cut2.diff','prepare_cut2.py']}),indent=2)+'\n')
print(json.dumps(dict(status='CUT2_REBOUND',manifest_sha256=sha(HERE/'cut2-prepared.json')),indent=2))
