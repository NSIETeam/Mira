import type {
  InboundEvent,
  KernelEventPayload,
} from "./types";

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
      return { type: "status", state: "turn_end", metadata: ev };
    case "goal_status":
      return { type: "status", state: "goal_status", metadata: ev };
    case "goal_state":
      return { type: "status", state: "goal_state", metadata: ev };
    case "ready":
      return { type: "status", state: "ready", metadata: ev };
    case "attached":
      return { type: "status", state: "attached", metadata: ev };
    case "runtime_model_updated":
      return { type: "status", state: "runtime_model_updated", metadata: ev };
    case "turn_model_updated":
      return { type: "status", state: "turn_model_updated", metadata: ev };
    case "session_updated":
      return { type: "status", state: "session_updated", metadata: ev };
    case "transcription_result":
      return { type: "status", state: "transcription_result", metadata: ev };
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
