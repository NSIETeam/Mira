export function chipTone(ok: boolean): string {
  return ok
    ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
    : "border-amber-500/20 bg-amber-500/10 text-amber-700";
}

export function operatorPanelTone(subject: string | null | undefined): string {
  switch (subject) {
    case "runtime":
    case "scheduler":
    case "lane":
    case "worker":
      return "border-cyan-200/80 bg-cyan-50/70";
    case "adapter":
    case "module":
    case "bridge":
      return "border-emerald-200/80 bg-emerald-50/60";
    case "board":
      return "border-amber-200/80 bg-amber-50/70";
    case "native":
      return "border-fuchsia-200/80 bg-fuchsia-50/60";
    case "fault":
    case "maintenance":
      return "border-rose-200/80 bg-rose-50/60";
    default:
      return "border-slate-200/80 bg-slate-50/70";
  }
}

export function toolFamilyChipTone(family: string): string {
  switch (family) {
    case "filesystem":
      return "border-emerald-300/80 bg-emerald-50 text-emerald-700";
    case "shell":
      return "border-slate-300/80 bg-slate-100 text-slate-700";
    case "web":
      return "border-cyan-300/80 bg-cyan-50 text-cyan-700";
    case "subagent":
    case "long-task":
      return "border-violet-300/80 bg-violet-50 text-violet-700";
    case "mcp":
      return "border-amber-300/80 bg-amber-50 text-amber-700";
    default:
      return "border-slate-300/80 bg-white text-slate-700";
  }
}

export function formatKernelTimestamp(value: unknown): string {
  const timestamp = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(timestamp) || timestamp <= 0) return "unknown";
  const date = new Date(timestamp);
  return formatClockTime(date);
}

export function formatClockTime(date: Date): string {
  if (Number.isNaN(date.getTime())) return "unknown";
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function formatKernelTimestampList(value: string): string {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const [name, rawTimestamp] = item.split(":");
      if (!name || rawTimestamp === undefined) return item;
      return `${name}:${formatKernelTimestamp(rawTimestamp)}`;
    })
    .join(", ");
}

export function formatBridgeCommandSummary(command: {
  target?: string | null;
  action?: string | null;
  status?: string | null;
  code?: number | null;
} | null | undefined): string {
  return `${command?.target ?? "runtime"}:${command?.action ?? "status"}:${command?.status ?? "ready"}:${command?.code ?? 0}`;
}

export function formatNativeCommandSummary(command: {
  target?: string | null;
  action?: string | null;
  status?: string | null;
  queue_depth?: number | null;
} | null | undefined): string {
  return `${command?.target ?? "target"}:${command?.action ?? "action"}:${command?.status ?? "queued"}:${command?.queue_depth ?? 0}`;
}

export function noneValue(value: string | null | undefined): string {
  return value && value.length ? value : "none";
}

export function findActionById<T extends { id?: string | null }>(
  actions: T[] | null | undefined,
  id: string,
): T | undefined {
  return actions?.find((action) => action.id === id);
}
