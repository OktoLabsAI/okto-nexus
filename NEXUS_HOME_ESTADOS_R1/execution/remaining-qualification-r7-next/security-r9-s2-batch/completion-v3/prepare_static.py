"""Exact host-template derivative, static only."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
original = (BASE / 's2-reported.js').read_text()
old = """      const dialog=page.getByRole('dialog',{name:'Activity detail'});
      await page.getByTestId('external-instance-'+cfg.owner.observed_instance_id).waitFor({timeout:10000});
      check('exact-observed-completion-open',await dialog.getByText('hst-security-reported-completion',{exact:true}).count()>=1,true);
"""
new = """      const dialog=page.getByRole('dialog',{name:'Canonical attention record',exact:true});
      const episode=dialog.getByTestId('external-completion-episode');
      const completionReference=episode.getByText('hst-security-reported-completion',{exact:true});
      await completionReference.waitFor({state:'visible',timeout:10000});
      const inspector=dialog.getByTestId('external-instance-'+cfg.owner.observed_instance_id);
      await inspector.waitFor({state:'visible',timeout:10000});
      const report=delivery.entry.external.find(exact);
      check('exact-observed-completion-open',
        report.workspace_id===cfg.reference.workspace_id&&report.last_report.sequence===2&&
        report.last_report.current_completion_ref==='hst-security-reported-completion'&&
        await completionReference.count()===1&&
        await inspector.getByText(cfg.owner.source_id,{exact:true}).count()===1&&
        await inspector.getByText(cfg.owner.observed_instance_id,{exact:true}).count()===1&&
        await inspector.getByText(cfg.reference.workspace_id,{exact:true}).count()===1&&
        await inspector.getByText('Instance · generation '+cfg.owner.generation,{exact:true}).count()===1&&
        /Sequence: 2(?:\\s|$)/.test(await inspector.innerText()),true);
"""
assert original.count(old) == 1
effective = original.replace(old, new, 1)
effective = effective.replace('const cfg=__CONFIG__,checks=[],requests=[];',
                              'const cfg=__CONFIG__,checks=[],requests=[],responses=[];', 1)
anchor = "  page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname}));"
assert effective.count(anchor) == 1
effective = effective.replace(anchor, anchor + "\n  page.on('response',r=>responses.push({method:r.request().method(),path:new URL(r.url()).pathname,status:r.status()}));", 1)
old_catch = "  }catch(error){return {status:'FAIL',error:String(error),checks,requests};}"
new_catch = """  }catch(error){
    const dialogs=await page.getByRole('dialog').evaluateAll(nodes=>nodes.map(node=>node.outerHTML.slice(0,100000))).catch(()=>[]);
    return {status:'FAIL',error:String(error),checks,requests,errorDiagnostics:{dialogs,responses}};
  }"""
assert effective.count(old_catch) == 1
effective = effective.replace(old_catch, new_catch, 1)
assert effective.count('__CONFIG__') == 1
# Preserve exact prior positive assertions, not merely their IDs.
for line in original.splitlines():
    if any("check('" + name + "'" in line for name in (
        'board-200', 'one-exact-reported-delivery', 'reported-not-native-verified',
        'not-verified-label', 'no-native-success-label')):
        assert line in effective
(HERE / 's2-reported.js').write_text(effective, encoding='utf-8')
(HERE / 'completion-only.diff').write_text(''.join(difflib.unified_diff(
    original.splitlines(True), effective.splitlines(True), fromfile='frozen S2 template', tofile='completion locator counterpart')), encoding='utf-8')
ast.parse((HERE / 'run.py').read_text())
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
manifest = {'kind': 'S2_COMPLETION_LOCATOR_ONLY_PREPARED_NOT_EXECUTED',
            'base_template_sha256': sha(BASE / 's2-reported.js'),
            'reader_manifest_sha256': sha(BASE / 'reader-v2/manifest.json'),
            'variant_pins': {name: sha(HERE / name) for name in (
                'run.py', 'prepare_static.py', 's2-reported.js', 'completion-only.diff', 'README.md')}}
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'manifest_sha256': sha(HERE / 'manifest.json'),
                  'completion_template_sha256': sha(HERE / 's2-reported.js'),
                  'allocated': False, 'runtime_executed': False}))
