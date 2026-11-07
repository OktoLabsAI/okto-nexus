// Public terminal guidance only. This module never accepts or resolves a credential.
export type ParticipantClient = 'claude' | 'codex' | 'generic';
export type CommandShell = 'powershell' | 'posix';
export interface ParticipantGuideOptions {
  origin: string;
  agentId: string;
  workspaceId: string;
  profile: string;
  client: ParticipantClient;
  shell: CommandShell;
}
export interface ParticipantGuideStep { id: string; title: string; command: string; explanation: string }
export type ParticipantGuideResult = {ok: false; message: string} | {
  ok: true; origin: string; plaintext: boolean; steps: ParticipantGuideStep[];
};

export function participantOrigin(value: string): {origin: string; loopback: boolean; plaintext: boolean} | null {
  if (/[\u0000-\u0020\u007f\s\\]/u.test(value)) return null;
  try {
    const url = new URL(value);
    const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
    if (!['https:', 'http:'].includes(url.protocol) || !url.hostname || url.username || url.password ||
        url.search || url.hash || url.port === '0' || (url.pathname !== '/' && url.pathname !== '') ||
        (url.protocol === 'http:' && !loopback)) return null;
    return {origin: url.origin, loopback, plaintext: url.protocol === 'http:'};
  } catch { return null; }
}

export function quoteParticipantArgument(value: string, shell: CommandShell): string {
  return shell === 'powershell'
    ? "'" + value.replace(/['\u2018\u2019\u201a\u201b]/g, character => character + character) + "'"
    : "'" + value.replace(/'/g, "'\"'\"'") + "'";
}

function publicIdentifier(value: string): boolean {
  return value.length > 0 && value.length <= 128 && value === value.trim() &&
    !/[\u0000-\u001f\u007f-\u009f]/u.test(value) && !/^nxs_[a-f0-9]{48}$/i.test(value);
}

export function buildParticipantGuide(options: ParticipantGuideOptions): ParticipantGuideResult {
  const address = participantOrigin(options.origin);
  if (!address) return {ok: false, message: 'Use an HTTPS Server origin without credentials, path, query or fragment. HTTP is limited to loopback.'};
  if (!publicIdentifier(options.agentId) || !publicIdentifier(options.workspaceId)) return {ok: false, message: 'Enter the existing agent ID and workspace ID. Never enter a key in these fields.'};
  if (!/^[A-Za-z0-9_-]{1,80}$/.test(options.profile) || !publicIdentifier(options.profile)) return {ok: false, message: 'Choose a profile using 1–80 letters, digits, hyphens or underscores. Never use a key as its name.'};
  if (!['claude', 'codex', 'generic'].includes(options.client) || !['powershell', 'posix'].includes(options.shell)) return {ok: false, message: 'Choose a supported guide and terminal.'};
  const quote = (value: string) => quoteParticipantArgument(value, options.shell);
  const profile = '--profile=' + quote(options.profile);
  const init = 'okto-nexus init --mode participant ' + profile;
  const doctor = 'okto-nexus doctor --mode participant ' + profile;
  const steps: ParticipantGuideStep[] = [
    {id: 'review', title: '1. Review on the client computer', command: init +
      ' --server=' + quote(address.origin) + ' --agent=' + quote(options.agentId) +
      ' --workspace-id=' + quote(options.workspaceId) + ' --client=' + options.client + ' --project . --plan',
    explanation: 'Run in the intended project folder. Review identity, workspace, origin and local effects before applying them.'},
    {id: 'apply', title: '2. Apply the exact review', command: init + ' --approve=REVIEW_REVISION',
    explanation: 'Replace REVIEW_REVISION with the revision just reviewed. Reuse this profile to recover the same setup after a lost reply.'},
  ];
  if (options.client !== 'generic') {
    const launch = 'okto-nexus participant launch ' + profile;
    steps.push(
      {id: 'launch-review', title: '3. Review a foreground launch', command: launch + ' --plan',
      explanation: 'Review the native executable, project and client configuration before starting it.'},
      {id: 'launch', title: '4. Launch after approval', command: launch + ' --approve=LAUNCH_REVIEW_REVISION',
      explanation: 'Replace LAUNCH_REVIEW_REVISION with the launch revision. The existing vault entry supplies only the new foreground process. The client retains its provider login and trust requirements; existing GUIs do not inherit this environment.'},
    );
  }
  steps.push(
    {id: 'doctor', title: 'Inspect the saved profile', command: doctor,
    explanation: 'Passive checks of this saved profile. Use another terminal while the foreground client is running.'},
    {id: 'mcp', title: 'Optionally check authentication and MCP', command: doctor + ' --check-server --check-mcp',
    explanation: 'Explicitly contacts the Server using the protected credential to initialize MCP and list tools. The check runs in the doctor process.'},
  );
  return {ok: true, origin: address.origin, plaintext: address.plaintext, steps};
}
