import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/connectionSessions.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText;
const {connectionSessions, SessionClosures} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const session = (id = 'session', state = 'READY', lease = 'ACTIVE') => ({scope: {agent_id:'claude',binding_id:'binding',executor_id:'host',
  server_id:'server',workspace_id:'workspace',workspace_binding_id:'folder',session_id:id}, lifecycle_state:state,lease_state:lease});

test('listing follows all pages and retains uncertain sessions until durable release', async () => {
  const cursors = [];
  const api = {binding: async () => ({agent_id:'claude',binding_id:'binding',executor_id:'host'}),
    sessions: async (_agent,_binding,after) => {cursors.push(after);return after ? {
      sessions:[session('failed','FAILED'),session('released','FAILED','CLOSED')],has_more:false} : {
      sessions:[session(),session('closed','CLOSED')],has_more:true,next_after_session_id:'closed'};}};
  assert.deepEqual((await connectionSessions(api,'claude',['binding'])).map(s => s.scope.session_id),['session','failed']);
  assert.deepEqual(cursors,['','closed']);
  api.binding = async () => ({agent_id:'another-agent'});
  await assert.rejects(connectionSessions(api,'claude',['binding']),/another agent/);
});

test('lost close response retries the same operation; a released session is not closed again', async () => {
  const closures = new SessionClosures(), requests = [], submissions = [];
  let current = session();
  const api = {session:async () => current, resolve:async request => {
    requests.push(request);return {...request,scope:current.scope,can_submit:true,operation_id:'close-op'};},
    submit:async resolution => {submissions.push(resolution);if(submissions.length===1)throw new Error('Network lost');return {error:null};}};
  await assert.rejects(closures.close(api,session()),/Network lost/);
  await closures.close(api,session());
  assert.equal(requests.length,1);
  assert.equal(requests[0].intent,'runtime.close');
  assert.strictEqual(submissions[0],submissions[1]);
  current = session('session','CLOSED','CLOSED');
  await closures.close(api,session());
  assert.equal(submissions.length,2);
});

test('closing refuses changed scope and rechecks a blocked review only on a later attempt', async () => {
  const closures = new SessionClosures(), requests = [];
  let submitted = 0;
  const api = {session:async () => session(),resolve:async request => {
    requests.push(request);return {scope:session().scope,can_submit:requests.length>1,blockers:['agent_recovering']};},
    submit:async () => {submitted++;return {error:null};}};
  await assert.rejects(closures.close(api,session()),/agent_recovering/);
  assert.equal(submitted,0);
  await closures.close(api,session());
  assert.equal(submitted,1);
  assert.notEqual(requests[0].client_intent_id,requests[1].client_intent_id);
  api.session = async () => ({...session(),scope:{...session().scope,agent_id:'another-agent'}});
  await assert.rejects(closures.close(api,session()),/scope changed/);
  assert.equal(submitted,1);
});
