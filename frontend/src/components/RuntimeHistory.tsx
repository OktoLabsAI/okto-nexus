import type { RuntimeScope } from '../runtimeApi';
import { RuntimeEventStream } from './RuntimeEventStream';

export function RuntimeHistory(props: {scope: RuntimeScope; harness?: string; allowMaximize?: boolean; onAccessLost?: () => void}) {
  return <RuntimeEventStream {...props} history/>;
}
