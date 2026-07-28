import type {
  GoalStateWsPayload,
  InboundEvent,
  KernelEventPayload,
} from "./types";

function metadataRow(metadata: unknown): Record<string, unknown> | null {
  return metadata && typeof metadata === "object"
    ? metadata as Record<string, unknown>
    : null;
}

function metadataString(row: Record<string, unknown> | null, key: string): string | null {
  if (!row) return null;
  const value = row[key];
  return typeof value === "string" ? value : null;
}

function metadataNumber(row: Record<string, unknown> | null, key: string): number | null {
  if (!row) return null;
  const value = row[key];
  return typeof value === "number" ? value : null;
}

function goalSummary(goal: unknown): string {
  const blob = metadataRow(goal);
  const uiSummary = metadataString(blob, "ui_summary");
  if (uiSummary && uiSummary.trim()) return uiSummary;
  const objective = metadataString(blob, "objective");
  if (objective && objective.trim()) return objective;
  return "";
}

export function goalStateFromKernelMetadata(metadata: unknown): GoalStateWsPayload | undefined {
  const row = metadataRow(metadata);
  if (!row || !("goal_state" in row) || !row.goal_state || typeof row.goal_state !== "object") {
    return undefined;
  }
  return row.goal_state as GoalStateWsPayload;
}

export function runStartedAtFromKernelMetadata(metadata: unknown): number | null {
  const row = metadataRow(metadata);
  const status = metadataString(row, "status") ?? "";
  const startedAt = metadataNumber(row, "started_at");
  if (status === "running" && startedAt !== null) return startedAt;
  return null;
}

export function turnCompletionFromKernelMetadata(metadata: unknown): {
  latencyMs?: number;
  turnId?: string;
} {
  const row = metadataRow(metadata);
  const latencyValue = metadataNumber(row, "latency_ms");
  const latencyMs = latencyValue !== null && latencyValue >= 0
    ? Math.round(latencyValue)
    : undefined;
  const turnId = metadataString(row, "turn_id") ?? undefined;
  return {
    ...(latencyMs !== undefined ? { latencyMs } : {}),
    ...(turnId ? { turnId } : {}),
  };
}

export function readyChatIdFromKernelMetadata(metadata: unknown): string | null {
  const row = metadataRow(metadata);
  const chatId = metadataString(row, "chat_id");
  if (!chatId || "turn_id" in row) return null;
  return chatId;
}

export function attachedChatIdFromKernelMetadata(metadata: unknown): string | null {
  const row = metadataRow(metadata);
  const chatId = metadataString(row, "chat_id");
  const sessionId = metadataString(row, "session_id");
  if (!chatId || !sessionId) return null;
  return chatId;
}

export function runtimeModelFromKernelMetadata(metadata: unknown): {
  modelName: string | null;
  modelPreset?: string | null;
} | null {
  const row = metadataRow(metadata);
  const modelName = metadataString(row, "model_name");
  if (modelName === null) return null;
  return {
    modelName: modelName || null,
    modelPreset: metadataString(row, "model_preset"),
  };
}

export function sessionUpdateFromKernelMetadata(metadata: unknown): {
  chatId: string;
  scope?: string;
  workspaceScope?: unknown;
} | null {
  const row = metadataRow(metadata);
  const chatId = metadataString(row, "chat_id");
  if (!chatId || !("workspace_scope" in row)) return null;
  return {
    chatId,
    scope: metadataString(row, "scope") ?? undefined,
    workspaceScope: row.workspace_scope,
  };
}

export function transcriptionResultFromKernelMetadata(metadata: unknown): {
  requestId: string;
  text: string;
} | null {
  const row = metadataRow(metadata);
  const requestId = metadataString(row, "request_id");
  const text = metadataString(row, "text");
  if (!requestId || text === null) return null;
  return { requestId, text };
}

export function transcriptionErrorFromKernelMetadata(metadata: unknown): {
  requestId?: string;
  detail: string;
} | null {
  const row = metadataRow(metadata);
  const detail = metadataString(row, "detail") ?? "";
  if (!detail) return null;
  const requestId = metadataString(row, "request_id") ?? undefined;
  return {
    ...(requestId ? { requestId } : {}),
    detail,
  };
}

export function workspaceScopeRejectionFromKernelMetadata(metadata: unknown): {
  reason?: string;
  chatId?: string;
} | null {
  const row = metadataRow(metadata);
  if (row.detail !== "workspace_scope_rejected") return null;
  return {
    ...(metadataString(row, "reason") ? { reason: metadataString(row, "reason") as string } : {}),
    ...(metadataString(row, "chat_id") ? { chatId: metadataString(row, "chat_id") as string } : {}),
  };
}

export function kernelStatusStateMatches(
  event: KernelEventPayload,
  ...states: string[]
): boolean {
  return event.type === "status" && typeof event.state === "string" && states.includes(event.state);
}

export function kernelErrorActionMatches(
  event: KernelEventPayload,
  action?: string,
): boolean {
  if (event.type !== "error") return false;
  if (action === undefined) return true;
  return event.action === action;
}

export function kernelCompletesSystemCommand(event: KernelEventPayload): boolean {
  return event.type === "message" || kernelStatusStateMatches(event, "turn_end");
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
