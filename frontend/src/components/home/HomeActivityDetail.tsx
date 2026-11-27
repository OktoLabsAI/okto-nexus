import {useEffect, useState} from 'react';
import {api} from '../../api';
import {readAttentionReference} from '../../attentionNavigation';
import {homeApi} from '../../homeApi';
import {homeSessionTarget, initialEntrySession} from '../../homeEntryInspection';
import {encodeHomeTarget, homeInspectionTarget, resolveHomeTarget} from '../../homeNavigation';
import type {HomeEntry, HomeResult, HomeSessionContext, HomeTarget} from '../../homeTypes';
import {HomeSessionInspection} from './HomeSessionInspection';

type ActivityRecord = Awaited<ReturnType<typeof readAttentionReference>>;
interface Summary {
  badge: string;
  tone?: 'success' | 'problem';
  result?: string;
  problem?: string;
}

function terminalOutcome(stage: string | null | undefined, result?: string | null, reason?: string | null): Summary {
  switch (stage?.toUpperCase()) {
    case 'SUCCESS':
    case 'SUCCEEDED':
    case 'COMPLETED': return {badge:'Success', tone:'success', result:result?.trim() || 'No result was recorded.'};
    case 'FAILED':
    case 'ERROR': return {badge:'Failed', tone:'problem', problem:reason?.trim() || 'The execution failed.'};
    case 'REJECTED': return {badge:'Not approved', tone:'problem', problem:reason?.trim() || 'The delivery did not meet its acceptance criteria.'};
    case 'CANCELLED':
    case 'INTERRUPTED': return {badge:'Interrupted', tone:'problem', problem:reason?.trim() || 'The work ended before completion.'};
    case 'OUTCOME_UNKNOWN':
    case 'RECONCILING': return {badge:'Unconfirmed', tone:'problem', problem:'The outcome could not be confirmed.'};
    case 'VERIFYING': return {badge:'Awaiting verification'};
    case 'READY':
    case 'ACTIVE':
    case 'RUNNING': return {badge:'In progress'};
    case 'FAILED_TO_START': return {badge:'Failed', tone:'problem', problem:reason?.trim() || 'The execution could not start.'};
    default: return reason?.trim() ? {badge:'Problem', tone:'problem', problem:reason.trim()} : {badge:'Pending'};
  }
}

function summarize(record: ActivityRecord | null, session: HomeSessionContext | undefined, retained?: HomeResult): Summary {
  const semantics = retained?.delivery_semantics;
  if (!record && retained) {
    if (semantics?.evidence === 'reported') return {badge:'Completion reported'};
    if (semantics?.verification === 'rejected' || semantics?.task_state === 'rejected') return terminalOutcome('REJECTED');
    if (semantics?.verification === 'pending') return {badge:'Awaiting verification'};
    const text = retained.preview && retained.truncated ? `${retained.preview}\n\nOutput truncated.` : retained.preview;
    return terminalOutcome(retained.outcome, text);
  }
  switch (record?.kind) {
    case 'execution': {
      const op = record.record;
      const output = op.result?.output_text ?? retained?.preview;
      const truncated = op.result ? op.result.output_truncated > 0 : retained?.truncated;
      const result = output && truncated ? `${output}\n\nOutput truncated.` : output;
      const stage = op.executor_stage ?? op.admission_state;
      if (semantics?.verification === 'rejected' || semantics?.task_state === 'rejected')
        return terminalOutcome('REJECTED', null, op.error?.message);
      const summary = terminalOutcome(stage, result, op.error?.message);
      return summary.tone === 'success' && semantics?.verification === 'pending'
        ? {badge:'Awaiting verification'} : summary;
    }
    case 'handoff': {
      const handoff = record.record;
      const reason = handoff.rejected_reason || handoff.verification_feedback || handoff.claimant_session_lost?.reason;
      if (handoff.status === 'CLAIMED' && handoff.verification_feedback?.trim())
        return terminalOutcome('REJECTED', null, handoff.verification_feedback);
      return terminalOutcome(handoff.status, handoff.result, reason);
    }
    case 'message': return record.record.runtime_result
      ? terminalOutcome(record.record.runtime_result.outcome, record.record.body ?? record.record.preview,
        record.record.body ?? record.record.preview)
      : {badge:'Message'};
    case 'external_observation': {
      const item = record.record.item;
      const report = item.last_report;
      return item.activity_state === 'blocked' ? {badge:'Problem reported', tone:'problem', problem:report?.reason_text || 'An external source reported that work is blocked.'}
        : {badge:'Activity reported'};
    }
    default: return session?.lifecycle_state === 'CLOSED' ? {badge:'Session ended'} : terminalOutcome(session?.lifecycle_state);
  }
}

export function HomeActivityDetail({target, entry, result, serverId, workspace, harness}: {
  target: HomeTarget; entry?: HomeEntry; result?: HomeResult; serverId: string; workspace: string | null; harness?: string;
}) {
  const [view, setView] = useState<'console' | 'conversation' | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [session, setSession] = useState<HomeSessionContext | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const key = encodeHomeTarget(target);

  useEffect(() => {
    const controller = new AbortController();
    const {signal} = controller;
    const expected = {server_id:serverId, workspace_id:workspace};
    setSummary(null); setSession(null); setCheckingSession(true); setView(null);
    const revoke = () => {
      controller.abort();
      setSession(null);
      setCheckingSession(false);
      setSummary({badge:'Unavailable', tone:'problem', problem:'Operator access is required to view this activity.'});
    };
    window.addEventListener('nexus-auth-expired', revoke);
    window.addEventListener('nexus-operator-logout', revoke);
    void (async () => {
      try {
        const resolved = await resolveHomeTarget(homeApi, target, expected, signal);
        if (!resolved.available) throw new Error('Unavailable activity');
        const canonical = homeInspectionTarget(resolved);
        const matches = (item: HomeResult) => item.detail_target && encodeHomeTarget(item.detail_target) === key;
        const retained = result && matches(result) ? result : entry?.results_preview.find(matches);
        const record = canonical.kind === 'session' ? null : await readAttentionReference(api, canonical, signal).catch(error=>{
          if (target.kind==='result' && canonical.kind==='execution' && retained && error.status===503) return null;
          throw error;
        });
        if (signal.aborted) return;
        if (record?.kind === 'execution' && record.record.scope.server_id !== serverId) throw new Error('Execution scope changed');
        setSummary(summarize(record, resolved.session_context, retained));

        const exactSession = resolved.session_context;
        const ref = record?.kind === 'execution' ? record.record.scope : entry ? initialEntrySession(entry, target) :
          target.kind==='result' && target.workspace_id ? {...target,workspace_id:target.workspace_id} : null;
        if (exactSession) setSession(exactSession);
        else if (ref?.workspace_id) {
          const related = await resolveHomeTarget(homeApi, homeSessionTarget(ref), expected, signal);
          if (!signal.aborted && related.available && related.session_context && (record?.kind !== 'execution' ||
              (['binding_id','workspace_binding_id','agent_id'] as const).every(field=>related.session_context?.[field] === record.record.scope[field])))
            setSession(related.session_context);
        }
      } catch (error) {
        if (signal.aborted) return;
        if ([401,403].includes((error as {status?:number}).status ?? 0)) {revoke(); return;}
        setSummary(current => current ?? {badge:'Unavailable', tone:'problem', problem:'This activity could not be loaded.'});
      } finally {
        if (!signal.aborted) setCheckingSession(false);
      }
    })();
    return () => {
      controller.abort();
      window.removeEventListener('nexus-auth-expired', revoke);
      window.removeEventListener('nexus-operator-logout', revoke);
    };
  }, [key, serverId, workspace]);

  if (!summary) return <p role="status">Loading activity…</p>;
  const badgeColor = summary.tone==='success' ? 'bg-emerald-100 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100'
    : summary.tone==='problem' ? 'bg-red-100 text-red-900 dark:bg-red-900 dark:text-red-100' : 'bg-surface-100 dark:bg-surface-800';
  return <section aria-label="Activity outcome" className="space-y-4 min-w-0">
    <span className={`inline-block rounded-full px-3 py-1 text-sm font-medium ${badgeColor}`}>{summary.badge}</span>
    {summary.result && <section aria-label="Result" className="space-y-1">
      <h3 className="font-semibold">Result:</h3><p className="whitespace-pre-wrap break-words text-sm">{summary.result}</p>
    </section>}
    {summary.problem && <section aria-label="Problem" className="space-y-1">
      <h3 className="font-semibold">Problem:</h3><p className="whitespace-pre-wrap break-words text-sm">{summary.problem}</p>
    </section>}
    <button type="button" className="btn btn-secondary" disabled={!session}
      title={!session && !checkingSession ? 'No session is linked to this activity' : undefined}
      onClick={()=>setView(current=>current==='console'?'conversation':'console')}>
      {view==='console'?'Show conversation':'Show console'}
    </button>
    {view && session && <HomeSessionInspection context={session} harness={harness}
      consoleView={view==='console'} conversationOnly={view==='conversation'}/>}
  </section>;
}
