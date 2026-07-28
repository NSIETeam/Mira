import type {
  GoalStateWsPayload,
  InboundEvent,
  KernelEventPayload,
} from "./types";

function goalSummary(goal: unknown): string {
  if (!goal || typeof goal !== "object") return "";
  const blob = goal as Record<string, unknown>;
  if (typeof blob.ui_summary === "string" && blob.ui_summary.trim()) return blob.ui_summary;
  if (typeof blob.objective === "string" && blob.objective.trim()) return blob.objective;
  return "";
}

export function goalStateFromKernelMetadata(metadata: unknown): GoalStateWsPayload | undefined {
  if (!metadata || typeof metadata !== "object") return undefined;
  const row = metadata as Record<string, unknown>;
  if (!("goal_state" in row) || !row.goal_state || typeof row.goal_state !== "object") {
    return undefined;
  }
  return row.goal_state as GoalStateWsPayload;
}

export function runStartedAtFromKernelMetadata(metadata: unknown): number | null {
  if (!metadata || typeof metadata !== "object") return null;
  const row = metadata as Record<string, unknown>;
  const status = typeof row.status === "string" ? row.status : "";
  const startedAt = typeof row.started_at === "number" ? row.started_at : null;
  if (status === "running" && startedAt !== null) return startedAt;
  return null;
}

export function toKernelEventPayload(ev: InboundEvent): KernelEventPayload {
  switch (ev.event) {
    case "delta":
      return { type: "message", text: ev.text, action: "delta", metadata: ev };
    case "reasoning_delta":
      return { type: "reasoning", text: ev.text, action: "delta", metadata: ev };
    case "reasoning_end":
      return { type: "reasoning", text: "text" in ev && typeof ev.text === "string" ? ev.text : "", action: "complete", metadata: ev };
    case "file_edit":
      return { type: "tool_result", action: "file_edit", metadata: ev };
    case "stream_end":
      return { type: "status", state: "stream_end", metadata: ev };
    case "turn_end":
      return {
        type: "status",
        text: goalSummary("goal_state" in ev ? ev.goal_state : undefined) || "turn completed",
        state: "turn_end",
        metadata: ev,
      };
    case "goal_status":
      return {
        type: "status",
        text: ev.status === "running" ? "goal runtime active" : "goal runtime idle",
        state: ev.status,
        metadata: ev,
      };
    case "goal_state":
      return {
        type: "status",
        text: goalSummary(ev.goal_state) || (ev.goal_state.active ? "active sustained goal" : "goal state cleared"),
        state: ev.goal_state.active ? "running" : "done",
        metadata: ev,
      };
    case "ready":
      return { type: "status", text: "kernel transport ready", state: "ready", metadata: ev };
    case "attached":
      return { type: "status", text: "shell attached to kernel", state: "ready", metadata: ev };
    case "runtime_model_updated":
      return {
        type: "status",
        text: typeof ev.model_name === "string" && ev.model_name.trim()
          ? `runtime model ${ev.model_name}`
          : "runtime model updated",
        state: "ready",
        metadata: ev,
      };
    case "turn_model_updated":
      return {
        type: "status",
        text: typeof ev.model_name === "string" && ev.model_name.trim()
          ? `turn model ${ev.model_name}`
          : "turn model updated",
        state: "running",
        metadata: ev,
      };
    case "session_updated":
      return {
        type: "status",
        text: typeof ev.scope === "string" && ev.scope.trim()
          ? `session ${ev.scope} updated`
          : "session updated",
        state: "ready",
        metadata: ev,
      };
    case "transcription_result":
      return {
        type: "status",
        text: "audio transcription ready",
        state: "done",
        metadata: ev,
      };
    case "transcription_error":
      return {
        type: "error",
        text: "detail" in ev ? (ev.detail ?? "") : "",
        action: "transcription_error",
        metadata: ev,
      };
    case "error":
      return {
        type: "error",
        text: "detail" in ev ? (ev.detail ?? "") : "",
        action: "error",
        metadata: ev,
      };
    case "message":
      if (ev.kind === "reasoning") {
        return { type: "reasoning", text: ev.text, action: "message", metadata: ev };
      }
      if (ev.kind === "tool_hint" || ev.kind === "progress") {
        return { type: "tool_call", text: ev.text, action: "trace", metadata: ev };
      }
      return { type: "message", text: ev.text, action: "complete", metadata: ev };
    default:
      return { type: "status", state: String((ev as { event?: string }).event ?? "unknown"), metadata: ev };
  }
}

export function kernelEventExtendsModelActivity(ev: InboundEvent): boolean {
  const kernelEvent = toKernelEventPayload(ev);
  return (
    kernelEvent.type === "message"
    || kernelEvent.type === "reasoning"
    || kernelEvent.type === "tool_call"
    || kernelEvent.type === "tool_result"
  );
}

export function isKernelToolCallEvent(ev: InboundEvent): boolean {
  return toKernelEventPayload(ev).type === "tool_call";
}
