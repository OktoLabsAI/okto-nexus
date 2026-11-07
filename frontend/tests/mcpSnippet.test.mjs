import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/participantGuide.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText;
const {buildParticipantGuide, participantOrigin, quoteParticipantArgument} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const options = (overrides = {}) => ({origin: 'https://nexus.example',
  agentId: 'reviewer', workspaceId: 'workspace-1', profile: 'reviewer',
  client: 'claude', shell: 'powershell', ...overrides});
const commands = value => {assert.equal(value.ok, true); return value.steps.map(step => step.command).join('\n');};

test('current HTTPS origin retains host and non-default port, without inventing 8202', () => {
  for (const origin of ['https://nexus.example', 'https://nexus.example:9443', 'https://[2001:db8::10]:9443']) {
    assert.equal(participantOrigin(origin).origin, origin);
    const text = commands(buildParticipantGuide(options({origin})));
    assert.ok(text.includes('--server=\'' + origin + '\''));
    assert.ok(!text.includes('http://') && !text.includes(':8202'));
  }
});

test('unsafe origins produce no command, including userinfo, query and remote plaintext', () => {
  for (const origin of ['http://nexus.example', 'https://user:token@nexus.example', 'https://nexus.example/mcp',
    'https://nexus.example?next=https://other.example', 'https://nexus.example#key', 'file:///config',
    'javascript:alert(1)', 'https://nexus.example\n', 'https://nexus.example\\other', '//nexus.example',
    'http://127.0.0.2:8202', 'https://nexus.example:0', 'https://nexus.example\u0000']) {
    const result = buildParticipantGuide(options({origin}));
    assert.equal(result.ok, false, origin);
    assert.equal(result.steps, undefined);
  }
});

test('valid origins generate public commands without a second approval gate', () => {
  assert.equal(buildParticipantGuide(options()).ok, true);
  for (const origin of ['http://127.0.0.1:8202', 'http://localhost:8202', 'http://[::1]:8202', 'https://localhost']) {
    const accepted = buildParticipantGuide(options({origin}));
    assert.equal(accepted.ok, true);
    assert.equal(accepted.plaintext, origin.startsWith('http:'));
  }
});

test('guidance carries no credential even when a legacy caller supplies an extra key property', () => {
  const marker = 'nxs_' + 'f'.repeat(48);
  for (const client of ['claude', 'codex', 'generic']) {
    const value = buildParticipantGuide(options({client, apiKey: marker}));
    assert.ok(!JSON.stringify(value).includes(marker));
    assert.ok(!commands(value).match(/export |Authorization:|--header|api_key=|--key=/));
  }
  for (const field of ['agentId', 'workspaceId', 'profile']) assert.equal(buildParticipantGuide(options({[field]: marker})).ok, false);
});

test('commands use existing CLI entry points and retain the same profile for recovery', () => {
  const result = buildParticipantGuide(options({client: 'codex'}));
  assert.equal(result.ok, true);
  assert.equal(result.steps[0].command, "okto-nexus init --mode participant --profile='reviewer' --server='https://nexus.example' --agent='reviewer' --workspace-id='workspace-1' --client=codex --project . --plan");
  assert.equal(result.steps[1].command, "okto-nexus init --mode participant --profile='reviewer' --approve=REVIEW_REVISION");
  assert.equal(result.steps[2].command, "okto-nexus participant launch --profile='reviewer' --plan");
  assert.equal(result.steps[3].command, "okto-nexus participant launch --profile='reviewer' --approve=LAUNCH_REVIEW_REVISION");
  assert.equal(result.steps[4].command, "okto-nexus doctor --mode participant --profile='reviewer'");
  assert.equal(result.steps[5].command, "okto-nexus doctor --mode participant --profile='reviewer' --check-server --check-mcp");
  assert.ok(!commands(result).match(/rotate|regenerate|new-agent|work |smoke /));
});

test('generic guidance makes no client launch or readiness claim', () => {
  const result = buildParticipantGuide(options({client: 'generic'}));
  assert.ok(commands(result).includes('--client=generic'));
  assert.ok(!commands(result).includes('participant launch'));
  assert.deepEqual(result.steps.map(step => step.id), ['review', 'apply', 'doctor', 'mcp']);
  assert.ok(result.steps.at(-1).explanation.includes('doctor process'));
});

test('shell quoting keeps punctuation in public IDs inside one argument', () => {
  const agentId = "worker'project";
  assert.equal(quoteParticipantArgument(agentId, 'powershell'), "'worker''project'");
  assert.equal(quoteParticipantArgument(agentId, 'posix'), "'worker'\"'\"'project'");
  assert.equal(quoteParticipantArgument('worker’project', 'powershell'), "'worker’’project'");
  for (const shell of ['powershell', 'posix']) {
    const value = buildParticipantGuide(options({agentId, shell}));
    assert.ok(commands(value).includes('--agent=' + quoteParticipantArgument(agentId, shell)));
  }
  for (const overrides of [{agentId: 'line\nbreak'}, {workspaceId: '\u001b[31m'}, {profile: '../other'}, {client: 'cursor'}, {shell: 'cmd'}]) {
    assert.equal(buildParticipantGuide(options(overrides)).ok, false);
  }
});
