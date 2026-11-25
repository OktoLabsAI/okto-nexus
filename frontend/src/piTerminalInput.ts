const navigation = new Map([
  ['\x1b[A', 'up'], ['\x1b[B', 'down'], ['\x1b[C', 'right'], ['\x1b[D', 'left'],
  ['\x1bOA', 'up'], ['\x1bOB', 'down'], ['\x1bOC', 'right'], ['\x1bOD', 'left'],
  ['\x1b[H', 'home'], ['\x1b[F', 'end'], ['\x1bOH', 'home'], ['\x1bOF', 'end'],
  ['\x1b[3~', 'delete'], ['\x7f', 'backspace'], ['\x08', 'backspace'],
  ['\r', 'enter'], ['\x1b[13;2u', 'newline'],
]);

export interface PiEdit {
  key: string;
  text?: string;
}

/** Map browser terminal input to the same literal draft edits used by the CLI. */
export function piTerminalEdits(data: string): PiEdit[] | null {
  const key = navigation.get(data);
  if (key) return [{key}];
  const start = '\x1b[200~', end = '\x1b[201~';
  const text = data.startsWith(start) && data.endsWith(end) ? data.slice(start.length, -end.length) : data;
  const clean = text.replace(/\r\n?/g, '\n');
  if (Array.from(clean).some(point => {
    const code = point.codePointAt(0)!;
    return (code < 32 && point !== '\t' && point !== '\n') || (code >= 127 && code <= 159);
  })) return [];
  const encoder = new TextEncoder();
  if (encoder.encode(clean).length > 12 * 1024) return null;
  const edits: PiEdit[] = [];
  let chunk = '', size = 0;
  for (const point of clean) {
    const bytes = encoder.encode(point).length;
    if (size + bytes > 4096) {
      edits.push({key: 'insert', text: chunk});
      chunk = '';
      size = 0;
    }
    chunk += point;
    size += bytes;
  }
  if (chunk) edits.push({key: 'insert', text: chunk});
  return edits;
}
