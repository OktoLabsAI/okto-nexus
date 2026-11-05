// This is only a dismissed-guide preference, never setup or identity state.
// Keep the existing key so an updated guide does not restart onboarding.

const STORAGE_KEY = "okto.nexus.onboarding.completed.v1";

export function isCompleted(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function markCompleted(): void {
  try {
    localStorage.setItem(STORAGE_KEY, "true");
  } catch {
    // ignore - onboarding will simply re-prompt next session
  }
}

export function reset(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

export const onboardingStorage = { isCompleted, markCompleted, reset, STORAGE_KEY };

export function shouldOfferIntroduction(completed: boolean, agents: unknown): boolean {
  // Unknown/error is not an empty installation. Existing identities also cover
  // work configured from another browser or the terminal, including inactive ones.
  // The reserved human operator is present even before the first project agent.
  return !completed && Array.isArray(agents) && agents.every(agent =>
    agent !== null && typeof agent === 'object' && agent.agent_id === 'operator');
}
