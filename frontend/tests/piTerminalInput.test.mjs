import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

const path = new URL('../src/piTerminalInput.ts', import.meta.url);
const compiled = ts.transpileModule(readFileSync(path, 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022},
}).outputText;
const {piTerminalEdits} = await import(`data:text/javascript,${encodeURIComponent(compiled)}`);

test('Enter submits an ordinary draft and pasted newlines stay literal', () => {
  assert.deepEqual(piTerminalEdits('\r'), [{key: 'enter'}]);
  assert.deepEqual(piTerminalEdits('\x1b[13;2u'), [{key: 'newline'}]);
  assert.deepEqual(piTerminalEdits('\x1b[200~um\r\ndois\x1b[201~'), [{key: 'insert', text: 'um\ndois'}]);
  assert.deepEqual(piTerminalEdits('\x1b[200~\r\x1b[201~'), [{key: 'insert', text: '\n'}]);
  assert.deepEqual(piTerminalEdits('\x1b[D'), [{key: 'left'}]);
  assert.deepEqual(piTerminalEdits('\x1b[200~test\x12\x1b[201~'), []);
  assert.deepEqual(piTerminalEdits('\x12'), []);
});

test('large inserts split by bytes without breaking a Unicode character', () => {
  const text = `a${'😀'.repeat(2048)}`;
  const edits = piTerminalEdits(text);
  assert.equal(edits.map(edit => edit.text).join(''), text);
  assert.ok(edits.every(edit => Buffer.byteLength(edit.text) <= 4096));
  assert.equal(piTerminalEdits('😀'.repeat(3073)), null);
});
