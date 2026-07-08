export const CURRENT_METRICS_SCHEMA_VERSION = "1.0.0";

const KEY = `okto-nexus:metrics-opt-in-prompt-dismissed:${CURRENT_METRICS_SCHEMA_VERSION}`;

export function isMetricsPromptDismissed(): boolean {
  return window.localStorage.getItem(KEY) !== null;
}

export function dismissMetricsPrompt(): void {
  window.localStorage.setItem(KEY, new Date().toISOString());
}

