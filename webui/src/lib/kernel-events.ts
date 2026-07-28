import type {
  GoalStateWsPayload,
  InboundEvent,
  KernelEventPayload,
  UITurnPhase,
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

function metadataChatId(row: Record<string, unknown> | null): string | null {
  return metadataString(row, "chat_id");
}

function metadataRequestId(row: Record<string, unknown> | null): string | null {
  return metadataString(row, "request_id");
}

function metadataTurnPhase(row: Record<string, unknown> | null): UITurnPhase | undefined {
  const value = metadataString(row, "turn_phase");
  return value as UITurnPhase | undefined;
}

function statusEvent(
  state: string,
  metadata: InboundEvent,
  text?: string,
): KernelEventPayload {
  return text
    ? { type: "status", text, state, metadata }
    : { type: "status", state, metadata };
}

function errorEvent(
  metadata: InboundEvent,
  action: string,
  text: string,
): KernelEventPayload {
  return {
    type: "error",
    text,
    action,
    metadata,
  };
}

function goalRuntimeText(status: string): string {
  return status === "running" ? "goal runtime active" : "goal runtime idle";
}

function goalStateText(goal: GoalStateWsPayload): string {
  return goalSummary(goal) || (goal.active ? "active sustained goal" : "goal state cleared");
}

function modelUpdateText(prefix: string, modelName: string): string {
  return modelName.trim() ? `${prefix} ${modelName}` : `${prefix} updated`;
}

function sessionUpdateText(scope: string | undefined): string {
  return scope && scope.trim() ? `session ${scope} updated` : "session updated";
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

export function turnFieldsFromKernelMetadata(metadata: unknown): {
  turn_id?: string;
  turn_phase?: UITurnPhase;
  turn_seq?: number;
} {
  const row = metadataRow(metadata);
  const turnId = metadataString(row, "turn_id") ?? undefined;
  const turnPhase = metadataTurnPhase(row);
  const turnSeq = metadataNumber(row, "turn_seq") ?? undefined;
  return {
    ...(turnId ? { turn_id: turnId } : {}),
    ...(turnPhase ? { turn_phase: turnPhase } : {}),
    ...(turnSeq !== undefined ? { turn_seq: turnSeq } : {}),
  };
}

export function assistantCompletionFromKernelMetadata(
  metadata: unknown | KernelMetadataSnapshot,
  extra: {
    content: string;
    media?: unknown;
    source?: unknown;
  },
): {
  content: string;
  latencyMs?: number;
  media?: unknown;
  source?: unknown;
} {
  const completion = "completion" in (metadata as Record<string, unknown>)
    ? (metadata as KernelMetadataSnapshot).completion
    : turnCompletionFromKernelMetadata(metadata);
  return {
    content: extra.content,
    ...(extra.media !== undefined ? { media: extra.media } : {}),
    ...(completion.latencyMs !== undefined ? { latencyMs: completion.latencyMs } : {}),
    ...(extra.source !== undefined ? { source: extra.source } : {}),
  };
}

export interface KernelMetadataSnapshot {
  goalState?: GoalStateWsPayload;
  runStartedAt: number | null;
  completion: {
    latencyMs?: number;
    turnId?: string;
  };
  readyChatId: string | null;
  attachedChatId: string | null;
  runtimeModel: {
    modelName: string | null;
    modelPreset?: string | null;
  } | null;
  sessionUpdate: {
    chatId: string;
    scope?: string;
    workspaceScope?: unknown;
  } | null;
  transcriptionResult: {
    requestId: string;
    text: string;
  } | null;
  transcriptionError: {
    requestId?: string;
    detail: string;
  } | null;
  workspaceScopeRejection: {
    reason?: string;
    chatId?: string;
  } | null;
}

export function kernelMetadataSnapshot(metadata: unknown): KernelMetadataSnapshot {
  return {
    goalState: goalStateFromKernelMetadata(metadata),
    runStartedAt: runStartedAtFromKernelMetadata(metadata),
    completion: turnCompletionFromKernelMetadata(metadata),
    readyChatId: readyChatIdFromKernelMetadata(metadata),
    attachedChatId: attachedChatIdFromKernelMetadata(metadata),
    runtimeModel: runtimeModelFromKernelMetadata(metadata),
    sessionUpdate: sessionUpdateFromKernelMetadata(metadata),
    transcriptionResult: transcriptionResultFromKernelMetadata(metadata),
    transcriptionError: transcriptionErrorFromKernelMetadata(metadata),
    workspaceScopeRejection: workspaceScopeRejectionFromKernelMetadata(metadata),
  };
}

export function readyChatIdFromKernelMetadata(metadata: unknown): string | null {
  const row = metadataRow(metadata);
  const chatId = metadataChatId(row);
  if (!chatId || "turn_id" in row) return null;
  return chatId;
}

export function attachedChatIdFromKernelMetadata(metadata: unknown): string | null {
  const row = metadataRow(metadata);
  const chatId = metadataChatId(row);
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
  const chatId = metadataChatId(row);
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
  const requestId = metadataRequestId(row);
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
  const requestId = metadataRequestId(row) ?? undefined;
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
  const reason = metadataString(row, "reason");
  const chatId = metadataChatId(row);
  return {
    ...(reason ? { reason } : {}),
    ...(chatId ? { chatId } : {}),
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

export function kernelMessageActionMatches(
  event: KernelEventPayload,
  action?: string,
): boolean {
  if (event.type !== "message") return false;
  if (action === undefined) return true;
  return event.action === action;
}

export function kernelReasoningActionMatches(
  event: KernelEventPayload,
  action?: string,
): boolean {
  if (event.type !== "reasoning") return false;
  if (action === undefined) return true;
  return event.action === action;
}

export function kernelToolCallActionMatches(
  event: KernelEventPayload,
  action?: string,
): boolean {
  if (event.type !== "tool_call") return false;
  if (action === undefined) return true;
  return event.action === action;
}

export function kernelToolResultActionMatches(
  event: KernelEventPayload,
  action?: string,
): boolean {
  if (event.type !== "tool_result") return false;
  if (action === undefined) return true;
  return event.action === action;
}

export function kernelExtendsStreamingActivity(event: KernelEventPayload): boolean {
  return (
    event.type === "message"
    || event.type === "reasoning"
    || event.type === "tool_call"
    || event.type === "tool_result"
  );
}

export function kernelStatusMatchesLifecycle(
  event: KernelEventPayload,
  ...states: string[]
): boolean {
  return kernelStatusStateMatches(event, ...states);
}

export function kernelCompletesSystemCommand(event: KernelEventPayload): boolean {
  return kernelMessageActionMatches(event) || kernelStatusStateMatches(event, "turn_end");
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
      return statusEvent("stream_end", ev);
    case "turn_end":
      return statusEvent(
        "turn_end",
        ev,
        goalSummary("goal_state" in ev ? ev.goal_state : undefined) || "turn completed",
      );
    case "goal_status":
      return statusEvent(ev.status, ev, goalRuntimeText(ev.status));
    case "goal_state":
      return statusEvent(ev.goal_state.active ? "running" : "done", ev, goalStateText(ev.goal_state));
    case "ready":
      return statusEvent("ready", ev, "kernel transport ready");
    case "attached":
      return statusEvent("ready", ev, "shell attached to kernel");
    case "runtime_model_updated":
      return statusEvent("ready", ev, modelUpdateText("runtime model", ev.model_name));
    case "turn_model_updated":
      return statusEvent("running", ev, modelUpdateText("turn model", ev.model_name));
    case "session_updated":
      return statusEvent("ready", ev, sessionUpdateText(ev.scope));
    case "transcription_result":
      return statusEvent("done", ev, "audio transcription ready");
    case "transcription_error":
      return errorEvent(ev, "transcription_error", "detail" in ev ? (ev.detail ?? "") : "");
    case "error":
      return errorEvent(ev, "error", "detail" in ev ? (ev.detail ?? "") : "");
    case "message":
      if (ev.kind === "reasoning") {
        return { type: "reasoning", text: ev.text, action: "message", metadata: ev };
      }
      if (ev.kind === "tool_hint" || ev.kind === "progress") {
        return { type: "tool_call", text: ev.text, action: "trace", metadata: ev };
      }
      return { type: "message", text: ev.text, action: "complete", metadata: ev };
    default:
      return statusEvent(String((ev as { event?: string }).event ?? "unknown"), ev);
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
