// Prepared: actual before/after JSON from the E16 canonical verification test.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import path from 'node:path';

const configured=JSON.parse(await readFile(process.env.HST_BACKEND_PRESENTATION_CONFIG,'utf8'));
const ts=(await import(pathToFileURL(configured.typescript).href)).default;
const moduleURL=async(name,replacements={})=>{
  const source=await readFile(path.join(configured.ui_source,name),'utf8');
  let code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
  for(const[from,to]of Object.entries(replacements))code=code.replaceAll(`'${from}'`,`'${to}'`).replaceAll(`"${from}"`,`"${to}"`);
  return 'data:text/javascript;base64,'+Buffer.from(code).toString('base64');
};
const contracts=await moduleURL('homeStateContracts.ts');
const {deliveryPresentation}=await import(await moduleURL('homeStatePresentation.ts',{'./homeStateContracts':contracts}));
const data=JSON.parse(await readFile(process.argv[2],'utf8'));
assert.equal(data.before.id,data.after.id);
assert.deepEqual(data.before.artifacts,data.after.artifacts);
assert.equal(data.before.artifacts.length,3);
assert.equal(data.before.delivery_semantics.scope,'turn');
assert.equal(data.before.delivery_semantics.task_state,'verifying');
assert.equal(data.before.delivery_semantics.historical,false);
assert.equal(data.after.delivery_semantics.scope,'turn');
assert.equal(data.after.delivery_semantics.task_state,'completed');
assert.equal(data.after.delivery_semantics.historical,false);
assert.notEqual(data.after.delivery_semantics.verification_evidence_ref,null);
assert.equal(typeof data.after.delivery_semantics.verification_evidence_ref,'string');
assert.ok(data.after.delivery_semantics.verification_evidence_ref.length>0);
assert.equal(data.before.delivery_semantics.verification,'pending');
assert.equal(data.after.delivery_semantics.verification,'approved');
assert.deepEqual(deliveryPresentation(data.before.delivery_semantics,{outcome:data.before.outcome,evidence:'canonical'}),
  {title:'Turn result available',badges:['Awaiting verification']});
assert.deepEqual(deliveryPresentation(data.after.delivery_semantics,{outcome:data.after.outcome,evidence:'canonical'}),
  {title:'Task completed',badges:['Delivery verified']});
console.log(JSON.stringify({same_delivery_verified:true,artifacts:3,presentation:'current pinned source, actual canonical API before/after data; not browser'}));
