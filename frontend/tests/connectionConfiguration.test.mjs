import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/connectionConfiguration.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText;
const {policyOnlySetup, emptyConnection} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

test('remote policy removes previously selected local binding without losing concurrency guards', () => {
  const original = {client_intent_id:'save-remote',agent_id:'subject',executor_id:'local-host',
    candidate_ref:'local-installation', inventory_revision:'inventory',workspace_id:'local-workspace',binding_id:'local-binding',
    baseline:{execution_revision:7,runtime_revision:3,defaults_revision:2,binding_revision:8,endpoint_revision:9},
    configuration:{...emptyConnection(),execution_location:'remote'}};
  const result = policyOnlySetup(original);
  assert.equal(result.binding_id,null);
  assert.equal(result.workspace_id,null);
  for (const key of ['executor_id','candidate_ref','inventory_revision']) assert.equal(result[key],'');
  assert.deepEqual(result.baseline,{execution_revision:7,runtime_revision:3,defaults_revision:2,binding_revision:null,endpoint_revision:null});
  assert.equal(result.configuration.execution_location,'remote');
  assert.equal(original.binding_id,'local-binding');
  assert.equal(original.baseline.binding_revision,8);
});
