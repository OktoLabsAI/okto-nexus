import assert from 'node:assert/strict';
import test from 'node:test';
import { moduleURL, section } from './homeR1Support.mjs';
const p = await import(await moduleURL('homePresentation.ts'));
test('claim, native acceptance, execution and unknown remain distinct', () => {
  assert.equal(new Set(['claimed', 'native_accepted', 'running', 'outcome_unknown'].map(p.homeStateLabel)).size, 4);
  assert.equal(p.homeStateLabel('UNRECOGNIZED'), 'Unknown');
  assert.equal(p.homeCounterLabel({ value: null, total_is_exact: false }), 'Not available');
  assert.equal(p.homeCounterLabel({ value: 0, total_is_exact: true }), '0');
  assert.equal(p.homeSectionLabel(section([], { status: 'unavailable' })), 'Unavailable');
});
test('result success keeps independent cleanup and verification; keys ignore titles', () => {
  assert.match(p.homeResultLabel({ outcome: 'SUCCEEDED', cleanup_state: 'pending' }), /cleanup pending/);
  assert.match(p.homeResultLabel({ outcome: 'SUCCEEDED', verification_state: 'pending' }), /verification pending/);
  assert.equal(p.homeActivityKey({ id: 'stable', title: 'one' }), p.homeActivityKey({ id: 'stable', title: 'two' }));
});
test('external activity is always reported and stale working never becomes native running', () => {
  assert.equal(p.homeExternalLabel({ freshness: 'stale', activity_state: 'working' }), 'External report · state unknown · stale · evidence unknown');
  assert.match(p.homeExternalLabel({ freshness: 'current', activity_state: 'working' }), /^External report/);
});
test('business feed templates hide tokens/heartbeat and retain decision/failure distinctions', () => {
  assert.equal(p.homeFeedLabel('native.token'), null); assert.equal(p.homeFeedLabel('session.heartbeat'), null);
  assert.notEqual(p.homeFeedLabel('handoff.verification_requested'), p.homeFeedLabel('handoff.verification_failed'));
  assert.match(p.homeFeedLabel('observation.completion'), /External/);
  assert.match(p.homeExternalLabel({ freshness: 'current', activity_state: 'working', last_report: { evidence: 'inferred' } }), /inferred$/);
});
