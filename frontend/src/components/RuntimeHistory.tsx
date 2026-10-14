import type { RuntimeScope } from '../runtimeApi';
import { RuntimeEventStream } from './RuntimeEventStream';

export function RuntimeHistory(props: {scope: RuntimeScope; harness?: string}) {
  return <RuntimeEventStream {...props} history/>;
}
