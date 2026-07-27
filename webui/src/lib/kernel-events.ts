import type {
  InboundEvent,
  KernelEventPayload,
} from "./types";

export function toKernelEventPayload(ev: InboundEvent): KernelEventPayload {
  switch (ev.event) {
    case "delta":
      return { type: "message", text: ev.text, metadata: ev };
    case "reasoning_delta":
    case "reasoning_end":
      return { type: "reasoning", text: "text" in ev ? ev.text : "", metadata: ev };
    case "file_edit":
      return { type: "tool_result", metadata: ev };
    case "stream_end":
    case "turn_end":
    case "goal_status":
    case "goal_state":
    case "ready":
    case "attached":
    case "runtime_model_updated":
    case "turn_model_updated":
    case "session_updated":
    case "transcription_result":
      return { type: "status", metadata: ev };
    case "transcription_error":
    case "error":
      return {
        type: "error",
        text: "detail" in ev ? (ev.detail ?? "") : "",
        metadata: ev,
      };
    case "message":
      if (ev.kind === "reasoning") {
        return { type: "reasoning", text: ev.text, metadata: ev };
      }
      if (ev.kind === "tool_hint" || ev.kind === "progress") {
        return { type: "tool_call", text: ev.text, metadata: ev };
      }
      return { type: "message", text: ev.text, metadata: ev };
    default:
      return { type: "status", metadata: ev };
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
