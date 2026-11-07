import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import test from 'node:test';
import ts from 'typescript';

const temporary = await mkdtemp(join(tmpdir(), 'nexus-attention-presentation-'));
let presentation;
try {
  const source = await readFile(new URL('../src/attentionPresentation.ts', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  await writeFile(join(temporary, 'presentation.mjs'), compiled);
  presentation = await import(pathToFileURL(join(temporary, 'presentation.mjs')).href);
} finally {
  await rm(temporary, { recursive: true, force: true });
}

const { attentionKinds, attentionActionLabels, attentionDescription, primaryAttentionAction,
  attentionAge, attentionSnoozeUntil, visibleAttentionPage, changeAttentionFilter, nextAttentionFocus, attentionSourceLabel } = presentation;

test('canonical and external kinds have distinct human labels, without echoing unknown codes', () => {
  assert.equal(Object.keys(attentionKinds).length, 16);
  assert.equal(new Set(Object.values(attentionKinds).map(value => value.title)).size, 16);
  for (const kind of Object.keys(attentionKinds)) {
    const value = attentionDescription({ kind });
    assert.ok(value.title.length > 0 && value.reason.length > 0);
    assert.ok(!value.title.includes('_'));
  }
  for (const kind of ['<img src=x onerror=alert(1)>', '__proto__', 'constructor', 'future_kind']) {
    assert.deepEqual(attentionDescription({ kind }), {
      title: 'Attention item', reason: 'Inspect the original record for its current state.',
    });
  }
  assert.match(attentionDescription({ kind: 'execution_outcome_unknown' }).reason, /not been confirmed/);
  assert.ok(!Object.values(attentionActionLabels).some(value => /^(approve|reject|retry|repeat|cancel|execute)\b/i.test(value)));
});

test('primary action opens only an allowed canonical control', () => {
  const item = { resolution: 'open', freshness: 'current', allowed_actions: ['inspect_approval', 'decide_native'] };
  assert.equal(primaryAttentionAction(item), 'decide_native');
  assert.equal(primaryAttentionAction({ ...item, allowed_actions: ['inspect_operation'] }), 'inspect_operation');
  assert.equal(primaryAttentionAction({ ...item, allowed_actions: ['respond_native', 'inspect_approval'] }), 'respond_native');
  assert.equal(primaryAttentionAction({ ...item, allowed_actions: ['inspect_operation', 'review_authority'] }), 'review_authority');
  assert.equal(primaryAttentionAction({ ...item, allowed_actions: ['retry_everything'] }), null);
  assert.equal(primaryAttentionAction({ ...item, allowed_actions: [] }), null);
});

test('history descriptions follow source resolution, never seen or snooze preferences', () => {
  const item = { kind: 'native_permission_pending', resolution: 'open' };
  assert.match(attentionDescription({ ...item, seen_state: { seen: true, snoozed: true } }).reason, /waiting for a permission/);
  assert.match(attentionDescription({ ...item, resolution: 'expired' }).reason, /has expired/);
  assert.match(attentionDescription({ ...item, resolution: 'resolved' }).reason, /resolved at its source/);
  assert.match(attentionDescription({ kind: 'result_unseen', resolution: 'resolved' }).reason, /result is available/);
});

test('expired, resolved or stale sources prefer inspection instead of decision controls', () => {
  for (const resolution of ['expired', 'resolved']) {
    assert.equal(primaryAttentionAction({ resolution, freshness: 'current', allowed_actions: ['decide_approval', 'inspect_approval'] }), 'inspect_approval');
    assert.equal(primaryAttentionAction({ resolution, freshness: 'current', allowed_actions: ['verify_handoff'] }), null);
  }
  for (const freshness of ['stale', 'unavailable']) {
    assert.equal(primaryAttentionAction({ resolution: 'open', freshness, allowed_actions: ['respond_native', 'inspect_approval'] }), 'inspect_approval');
    assert.equal(primaryAttentionAction({ resolution: 'open', freshness, allowed_actions: ['review_authority', 'inspect_operation'] }), 'inspect_operation');
  }
  assert.equal(primaryAttentionAction({ resolution: 'resolved', freshness: 'current', allowed_actions: ['inspect_result'] }), 'inspect_result');
});

test('source names are plain known labels, including prototype-like unknown values', () => {
  assert.equal(attentionSourceLabel('execution_native_request'), 'Native request');
  assert.equal(attentionSourceLabel('runtime_result_maintenance'), 'Cleanup record');
  for (const source of ['<script>bad</script>', '__proto__', 'constructor', 'toString', 'future']) {
    assert.equal(attentionSourceLabel(source), 'Source record');
  }
});

test('external attention exposes inspection only and preserves observational wording', () => {
  for (const kind of ['external_blocked', 'external_completion_unseen', 'external_observation_stale']) {
    assert.equal(primaryAttentionAction({kind, source_type: 'external_observation', resolution: 'open', freshness: 'current',
      allowed_actions: ['decide_approval', 'verify_handoff', 'inspect_external_observation']}), 'inspect_external_observation');
    assert.equal(primaryAttentionAction({kind, resolution: 'open', freshness: 'current', allowed_actions: ['decide_approval']}), null);
  }
  assert.match(attentionDescription({kind: 'external_blocked'}).reason, /not an approval request/);
  assert.match(attentionDescription({kind: 'external_completion_unseen', resolution: 'resolved'}).reason, /does not confirm/);
  assert.match(attentionDescription({kind: 'external_observation_stale', resolution: 'expired'}).reason, /does not mean idle or offline/);
  assert.equal(attentionSourceLabel('external_observation'), 'Observed external instance');
});

test('protected or differently scoped snapshots are never presented', () => {
  const page = { filters: { workspace_id: 'one', state: 'active', seen: 'all' }, items: [], total: 0 };
  for (const status of ['forbidden', 'disabled']) {
    assert.equal(visibleAttentionPage({ status, page }, { workspace_id: 'one' }), null);
  }
  assert.equal(visibleAttentionPage({ status: 'ready', page }, { workspace_id: 'two' }), null);
  assert.equal(visibleAttentionPage({ status: 'ready', page }, { workspace_id: 'one', agent_id: 'other' }), null);
  assert.equal(visibleAttentionPage({ status: 'ready', page }, { workspace_id: 'one', seen: 'unseen' }), null);
  assert.equal(visibleAttentionPage({ status: 'ready', page: null }, {}), null);
  assert.equal(visibleAttentionPage({ status: 'stale', page }, { workspace_id: 'one' }), page);
});

test('matching page retains its own filtered counts and never substitutes global summary', () => {
  const page = { filters: { category: 'watch', state: 'all', seen: 'all' }, items: [{ attention_id: 'one' }], total: 3,
    counts: { action_required: 0, watch: 3 } };
  const state = { status: 'ready', page, summary: { total: 800, counts: { action_required: 700, watch: 100 } } };
  const selected = visibleAttentionPage(state, { category: 'watch', state: 'all' });
  assert.equal(selected, page);
  assert.equal(selected.total, 3);
  assert.equal(selected.counts.watch, 3);
});

test('selecting snoozed includes inactive occurrences and keeps the current scope', () => {
  const filters = { workspace_id: 'workspace', agent_id: 'agent', category: 'watch', state: 'active', seen: 'all' };
  const next = changeAttentionFilter(filters, 'seen', 'snoozed');
  assert.deepEqual(next, { ...filters, state: 'all', seen: 'snoozed' });
  assert.equal(filters.state, 'active');
  assert.equal(filters.seen, 'all');
  assert.deepEqual(changeAttentionFilter({ workspace_id: 'workspace' }, 'seen', 'snoozed'),
    { workspace_id: 'workspace', state: 'all', seen: 'snoozed' });
  assert.deepEqual(changeAttentionFilter(next, 'agent_id', undefined),
    { workspace_id: 'workspace', category: 'watch', state: 'all', seen: 'snoozed' });
});

test('age handles timezone offsets, future timestamps and invalid dates without negative ages', () => {
  const now = Date.parse('2026-11-06T15:00:00Z');
  assert.equal(attentionAge('2026-11-06T15:00:01Z', now), 'Just now');
  assert.equal(attentionAge('2026-11-06T11:59:00-03:00', now), '1m ago');
  assert.equal(attentionAge('2026-11-06T13:00:00Z', now), '2h ago');
  assert.equal(attentionAge('2026-11-04T15:00:00Z', now), '2d ago');
  assert.equal(attentionAge('not-a-date', now), 'Unknown age');
});

test('snooze presets emit bounded UTC deadlines without a source mutation', () => {
  const now = Date.parse('2026-11-06T15:00:00Z');
  assert.equal(attentionSnoozeUntil(15, now), '2026-11-06T15:15:00.000Z');
  assert.equal(attentionSnoozeUntil(60, now), '2026-11-06T16:00:00.000Z');
  assert.equal(attentionSnoozeUntil(1440, now), '2026-11-07T15:00:00.000Z');
  for (const duration of [0, -1, 43201, NaN, Infinity]) assert.throws(() => attentionSnoozeUntil(duration, now));
});

test('focus stays on its record or moves to the next surviving row, then the previous row or heading', () => {
  const prior = ['a', 'b', 'c', 'd'];
  assert.equal(nextAttentionFocus(prior, ['a', 'b', 'c'], 'b'), 'b');
  assert.equal(nextAttentionFocus(prior, ['a', 'c', 'd'], 'b'), 'c');
  assert.equal(nextAttentionFocus(prior, ['a', 'b'], 'd'), 'b');
  assert.equal(nextAttentionFocus(prior, ['new'], 'b'), 'new');
  assert.equal(nextAttentionFocus(prior, [], 'b'), null);
  assert.deepEqual(prior, ['a', 'b', 'c', 'd']);
});
