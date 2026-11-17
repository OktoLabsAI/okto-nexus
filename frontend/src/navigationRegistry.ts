/** Presentation only. Existing API authorization and feature checks remain authoritative. */
export const VIEW_IDS = ['Home', 'Attention', 'Graph', 'Messages', 'Handoffs', 'Meta-harness',
  'Events', 'Artifacts', 'Memory', 'Workspaces', 'Agents', 'Registry', 'Policies', 'Guardrails',
  'Communication', 'Approvals', 'Runtimes', 'Execution log', 'Settings', 'Advanced'] as const;
export type ViewId = typeof VIEW_IDS[number];
export type NavigationSection = 'primary' | 'secondary' | 'advanced' | 'utility';
export type AdvancedGroupId = 'agents-execution' | 'policies-control' | 'history-diagnostics' | 'system-data';
export interface NavigationFeatures { memoryEnabled: boolean }
export interface NavigationEntry {
  readonly id: ViewId;
  readonly label: string;
  readonly description: string;
  readonly section: NavigationSection;
  readonly group?: AdvancedGroupId;
  readonly feature?: 'memory';
}
export const ADVANCED_GROUPS: readonly { readonly id: AdvancedGroupId; readonly label: string; readonly description: string }[] = [
  {id: 'agents-execution', label: 'Agents and execution', description: 'Configure agents, capabilities and runtime connections.'},
  {id: 'policies-control', label: 'Policies and control', description: 'Review policies, safeguards and approval history.'},
  {id: 'history-diagnostics', label: 'History and diagnostics', description: 'Inspect messages, work history and project health.'},
  {id: 'system-data', label: 'System and data', description: 'Manage shared data and system configuration.'},
];
export const NAVIGATION_REGISTRY: readonly NavigationEntry[] = [
  {id: 'Home', label: 'Home', section: 'primary', description: 'Request work and follow its progress.'},
  {id: 'Meta-harness', label: 'Conversations', section: 'primary', description: 'Talk to agents and continue a conversation.'},
  {id: 'Graph', label: 'Graph', section: 'primary', description: 'Explore relationships, messages and work visually.'},
  {id: 'Artifacts', label: 'Artifacts', section: 'primary', description: 'Find files and other delivered artifacts.'},
  {id: 'Advanced', label: 'Advanced', section: 'secondary', description: 'Open administration, history and diagnostics.'},
  {id: 'Attention', label: 'Needs attention', section: 'utility', description: 'Review questions, approvals and issues requiring attention.'},
  {id: 'Agents', label: 'Agent administration', section: 'advanced', group: 'agents-execution', description: 'Inspect agent identities and configure their connections.'},
  {id: 'Runtimes', label: 'Runtime administration', section: 'advanced', group: 'agents-execution', description: 'Inspect runtime connections and diagnose execution.'},
  {id: 'Registry', label: 'Tags and capabilities', section: 'advanced', group: 'agents-execution', description: 'Manage the existing capability and tag catalog.'},
  {id: 'Communication', label: 'Communication styles', section: 'advanced', group: 'agents-execution', description: 'Configure how agents communicate.'},
  {id: 'Policies', label: 'Policies', section: 'advanced', group: 'policies-control', description: 'Inspect and configure policy definitions.'},
  {id: 'Guardrails', label: 'Guardrails', section: 'advanced', group: 'policies-control', description: 'Inspect and configure protective rules.'},
  {id: 'Approvals', label: 'Approval history', section: 'advanced', group: 'policies-control', description: 'Review approval history and administration.'},
  {id: 'Messages', label: 'Message history', section: 'advanced', group: 'history-diagnostics', description: 'Inspect the technical history of messages and deliveries.'},
  {id: 'Handoffs', label: 'Work delegations', section: 'advanced', group: 'history-diagnostics', description: 'Inspect delegated work and its full history.'},
  {id: 'Events', label: 'Events', section: 'advanced', group: 'history-diagnostics', description: 'Inspect recorded events and their details.'},
  {id: 'Execution log', label: 'Execution records', section: 'advanced', group: 'history-diagnostics', description: 'Diagnose execution receipts, errors and authorization decisions.'},
  {id: 'Workspaces', label: 'Project health', section: 'advanced', group: 'history-diagnostics', description: 'Inspect project health and activity.'},
  {id: 'Memory', label: 'Shared memory', section: 'advanced', group: 'system-data', feature: 'memory', description: 'Inspect shared memory when enabled on this Server.'},
  {id: 'Settings', label: 'System settings', section: 'advanced', group: 'system-data', description: 'Manage system configuration and data settings.'},
];
export const PRIMARY_NAVIGATION = NAVIGATION_REGISTRY.filter(entry => entry.section === 'primary');
export const SECONDARY_NAVIGATION = NAVIGATION_REGISTRY.filter(entry => entry.section === 'secondary');

export function getNavigationEntry(id: ViewId): NavigationEntry {
  const entry = NAVIGATION_REGISTRY.find(value => value.id === id);
  if (!entry) throw new Error('Unknown navigation destination.');
  return entry;
}
/** Resolve known labels and legacy IDs; never fall back to an unrelated destination. */
export function resolveNavigationId(value: unknown): ViewId | null {
  if (typeof value !== 'string') return null;
  return NAVIGATION_REGISTRY.find(entry => entry.id === value || entry.label === value)?.id ?? null;
}
export function isNavigationVisible(entry: NavigationEntry, features: NavigationFeatures): boolean {
  return entry.feature !== 'memory' || features.memoryEnabled;
}
export function getAdvancedGroups(features: NavigationFeatures) {
  return ADVANCED_GROUPS.map(group => ({...group, entries: NAVIGATION_REGISTRY.filter(entry =>
    entry.section === 'advanced' && entry.group === group.id && isNavigationVisible(entry, features))}));
}
export interface NavigationBreadcrumb { id: ViewId; label: string }
export function getNavigationBreadcrumb(id: ViewId): NavigationBreadcrumb[] {
  const entry = getNavigationEntry(id);
  const current = {id: entry.id, label: entry.label};
  if (entry.section !== 'advanced') return [current];
  const group = ADVANCED_GROUPS.find(value => value.id === entry.group);
  return [{id: 'Advanced', label: 'Advanced'}, ...(group ? [{id: 'Advanced' as const, label: group.label}] : []), current];
}
/** Used for sidebar selection only, never as an access-control decision. */
export function getNavigationSectionId(id: ViewId): ViewId {
  return getNavigationEntry(id).section === 'advanced' ? 'Advanced' : id;
}
