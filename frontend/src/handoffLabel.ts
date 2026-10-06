import type { GraphHandoff } from "./api";

export function handoffLabel(handoff: Pick<GraphHandoff, "handoff_id" | "payload">): string {
  const payload = handoff.payload;
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    const fields = payload as Record<string, unknown>;
    for (const value of [fields.title, fields.subject]) {
      if (typeof value === "string" && value.trim()) return value.trim();
    }
  }
  return handoff.handoff_id;
}
