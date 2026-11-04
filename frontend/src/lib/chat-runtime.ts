import type { ChatAgentStep } from "@/types/chat";

/** Replaces a step with the same id, otherwise appends it; execution steps arrive in order and are updated in place. */
export function upsertAgentStep(current: ChatAgentStep[], next: ChatAgentStep): ChatAgentStep[] {
  return current.some((step) => step.id === next.id)
    ? current.map((step) => (step.id === next.id ? next : step))
    : [...current, next];
}

/** Marks still-running steps as stopped after an explicit stop; finished steps keep their status. */
export function markRunningStepsStopped(steps: ChatAgentStep[], detail: string): ChatAgentStep[] {
  if (!steps.some((step) => step.status === "running")) {
    return steps;
  }
  return steps.map((step) => (step.status === "running" ? { ...step, status: "stopped", detail } : step));
}

/** Session ids with a turn in flight, excluding the placeholder used before a session exists. */
export function runningSessionIds(
  sessions: Record<string, { isSending: boolean }>,
  placeholderId: string
): string[] {
  return Object.keys(sessions).filter((id) => id !== placeholderId && sessions[id].isSending);
}
