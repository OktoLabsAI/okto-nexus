import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

async function load(path) {
  const source = await readFile(new URL(path, import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, {compilerOptions: {
    module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022,
  }}).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
}
const {displayName, otherMetadata, identityMetadata} = await load('../src/projectIdentity.ts');
const {shouldOfferIntroduction} = await load('../src/components/onboarding/onboardingStorage.ts');

test('editing or clearing a display name preserves unrelated typed metadata', () => {
  const original = {display_name: 'Project', nested: {values: [false, null, 3]}, code: '007'};
  const before = structuredClone(original);
  assert.equal(displayName(original), 'Project');
  assert.deepEqual(identityMetadata(otherMetadata(original), '  Writer  '), {...original, display_name: 'Writer'});
  assert.deepEqual(identityMetadata(otherMetadata(original), ' '), {nested: original.nested, code: '007'});
  assert.deepEqual(original, before);
});

test('legacy non-string display metadata survives an untouched edit', () => {
  for (const display_name of [false, 4, null, {custom: 'value'}]) {
    const original = {display_name, keep: true};
    assert.equal(displayName(original), '');
    assert.deepEqual(identityMetadata(otherMetadata(original), ''), original);
  }
  assert.equal(displayName(undefined), '');
  assert.deepEqual(identityMetadata(otherMetadata(null), 'Name'), {display_name: 'Name'});
});

test('only a confirmed empty installation offers introduction, ignoring the reserved operator', () => {
  assert.equal(shouldOfferIntroduction(false, []), true);
  assert.equal(shouldOfferIntroduction(false, [{agent_id: 'operator'}]), true);
  for (const value of [undefined, null, {}, [null], [{}], [{agent_id: 'operator'}, {}]]) {
    assert.equal(shouldOfferIntroduction(false, value), false);
  }
});

test('existing identities and dismissed guidance never force setup again', () => {
  for (const is_active of [true, false]) {
    assert.equal(shouldOfferIntroduction(false, [{agent_id: 'operator'}, {agent_id: 'project', is_active}]), false);
  }
  assert.equal(shouldOfferIntroduction(true, []), false);
  assert.equal(shouldOfferIntroduction(true, [{agent_id: 'operator'}]), false);
});
