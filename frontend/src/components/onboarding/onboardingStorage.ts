// Versioned localStorage flag gating the first-run OnboardingModal (mirrors
// the Okto Pulse onboardingStorage pattern). Bumping the version (v1 -> v2)
// re-shows the intro to every returning operator on the next boot, with no
// server-side migration.

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
