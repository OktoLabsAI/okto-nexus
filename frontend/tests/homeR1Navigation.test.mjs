import assert from 'node:assert/strict';
import test from 'node:test';
import { moduleURL } from './homeR1Support.mjs';
const { encodeHomeTarget, decodeHomeTarget, homeTargetSearch, resolveHomeTarget, homeInspectionTarget } =
  await import(await moduleURL('homeNavigation.ts'));
const target = { kind: 'execution', server_id: 'server:/one', workspace_id: 'ws & one', executor_id: 'host:/one',
  session_id: 'session?/ü', operation_id: 'op:1/2#3' };
test('opaque IDs roundtrip canonically without title/path/content and without delimiter aliases', () => {
  assert.deepEqual(decodeHomeTarget(encodeHomeTarget(target)), target);
  assert.equal(encodeHomeTarget(Object.fromEntries(Object.entries(target).reverse())), encodeHomeTarget(target));
  const search = new URLSearchParams(homeTargetSearch(target)); assert.deepEqual(decodeHomeTarget(search.get('home_target')), target);
  assert.equal(decodeHomeTarget(JSON.stringify({ ...target, command: 'do something' })), null);
  assert.equal(decodeHomeTarget(JSON.stringify({ ...target, url: 'https://untrusted' })), null);
  assert.equal(decodeHomeTarget('{bad json'), null);
  assert.equal(decodeHomeTarget(JSON.stringify({ ...target, operation_id: '' })), null);
});
test('resolver rejects mismatched workspace/server before request and changed result afterward', async () => {
  let calls = 0; const api = { target: async () => { calls++; return { version: 1, available: true, source_revision: 'r', target }; } };
  await assert.rejects(resolveHomeTarget(api, target, { server_id: 'other', workspace_id: null }));
  await assert.rejects(resolveHomeTarget(api, target, { server_id: target.server_id, workspace_id: 'other' })); assert.equal(calls, 0);
  await resolveHomeTarget(api, target, { server_id: target.server_id, workspace_id: target.workspace_id }); assert.equal(calls, 1);
  await assert.rejects(resolveHomeTarget({ target: async () => ({ version: 1, available: true, target: { ...target, operation_id: 'latest' } }) },
    target, { server_id: target.server_id, workspace_id: null }));
});
test('canonical inspector requires resolved actor and never guesses latest or turns external into execution', () => {
  assert.equal(homeInspectionTarget({ version: 1, available: true, source_revision: 'r', target }).kind, 'unavailable');
  const actual = homeInspectionTarget({ version: 1, available: true, source_revision: 'r', target, agent_id: 'A' });
  assert.equal(actual.operation, target.operation_id); assert.equal(actual.session, target.session_id); assert.equal(actual.agent, 'A');
  const external = { kind: 'external_observation', server_id: 's', workspace_id: 'w', source_id: 'src', observed_instance_id: 'i', generation: 1 };
  assert.equal(homeInspectionTarget({ target: external, available: true, source_revision: 'r', agent_id: 'A' }).kind, 'external_observation');
  assert.equal(decodeHomeTarget(JSON.stringify({ ...external, generation: 0 })), null);
});
