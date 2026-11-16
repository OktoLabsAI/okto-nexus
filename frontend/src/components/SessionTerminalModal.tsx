import type { MetaHarnessSession } from '../api';
import { AgentActionModal } from './AgentActionModal';
import { SessionExecutionPanel } from './SessionExecutionPanel';

export function SessionTerminalModal({session, onClose}: {session: MetaHarnessSession; onClose: () => void}) {
  return <AgentActionModal title={`Terminal · ${session.scope.agent_id}`} wide guardChanges={false} onClose={onClose}>
    <SessionExecutionPanel session={session} harness={session.harness} host={session.host}/>
  </AgentActionModal>;
}
