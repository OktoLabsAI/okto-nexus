import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/graph/agentColor.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022},
}).outputText;
const {
  hashOf,
  isHexColor,
  autoColor,
  agentColor,
  gradientFor,
  relativeLuminance,
  textColorFor,
} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

test('hashOf is deterministic and returns an unsigned 32-bit integer', () => {
  const first = hashOf('agent-alpha');
  assert.equal(hashOf('agent-alpha'), first);
  assert.equal(Number.isInteger(first), true);
  assert.ok(first >= 0);
  assert.ok(first <= 0xffffffff);
});

test('isHexColor accepts three- and six-digit hex values, including surrounding whitespace', () => {
  for (const value of ['#fff', '#FFFFFF', ' #abc ']) {
    assert.equal(isHexColor(value), true, `expected ${JSON.stringify(value)} to be accepted`);
  }
});

test('isHexColor rejects malformed values and non-string inputs', () => {
  for (const value of ['fff', '#ffff', '', '#12', '#ggg', null, 123]) {
    assert.equal(isHexColor(value), false, `expected ${JSON.stringify(value)} to be rejected`);
  }
});

test('autoColor is deterministic for the same agent id', () => {
  assert.equal(autoColor('agent-alpha'), autoColor('agent-alpha'));
});

test('autoColor usually assigns different colors to different agent ids', () => {
  const colors = ['agent-alpha', 'agent-beta', 'agent-gamma'].map(autoColor);
  assert.equal(new Set(colors).size, colors.length);
  for (const color of colors) assert.match(color, /^#[0-9a-f]{6}$/i);
});

test('agentColor preserves a valid stored color after trimming whitespace', () => {
  assert.equal(agentColor('agent-alpha', ' #112233 '), '#112233');
});

test('agentColor falls back to the identity color for malformed or missing stored colors', () => {
  const expected = autoColor('agent-alpha');
  assert.equal(agentColor('agent-alpha', 'bad'), expected);
  assert.equal(agentColor('agent-alpha', null), expected);
  assert.equal(agentColor('agent-alpha'), expected);
});

test('textColorFor selects dark ink for white and light ink for black', () => {
  assert.equal(textColorFor('#ffffff'), '#0b1220');
  assert.equal(textColorFor('#000000'), '#f8fafc');
});

test('relativeLuminance returns the expected endpoints for black and white', () => {
  assert.ok(Math.abs(relativeLuminance('#000000') - 0) < 1e-9);
  assert.ok(Math.abs(relativeLuminance('#ffffff') - 1) < 1e-9);
});

test('gradientFor returns a CSS linear gradient with two hex color stops', () => {
  const gradient = gradientFor('#336699');
  assert.match(gradient, /^linear-gradient\(135deg, #[0-9a-f]{6}, #[0-9a-f]{6}\)$/i);
});
