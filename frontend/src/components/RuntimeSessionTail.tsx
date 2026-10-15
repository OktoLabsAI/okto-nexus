import type { RuntimeScope } from '../runtimeApi';
import { RuntimeEventStream } from './RuntimeEventStream';

export function RuntimeSessionTail(props: {scope: RuntimeScope; active: boolean; harness?: string}) {
  return <RuntimeEventStream {...props}/>;
}
