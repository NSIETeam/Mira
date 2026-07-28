export type HostKernelStatus = {
  privilege: "root" | "user" | "unknown";
  health: "healthy" | "attention" | "offline" | "unknown";
  maintenance: "maintenance" | "live" | "unknown";
  runtimeState: "healthy" | "attention" | "offline" | "maintenance";
  runtimeSeverity: "normal" | "warning" | "critical";
  privilegeSeverity: "elevated" | "restricted" | "unknown";
  connected: boolean;
  alert: boolean;
  summary: string;
};

export type HostChromePresentation = {
  healthBadge: { label: string; className: string } | null;
  maintenanceBadge: { label: string; className: string } | null;
  privilegeBadge: { label: string; className: string } | null;
  healthDotClass: string;
  chromeCapsuleClass: string;
  chromeCapsuleMotionClass: string;
  visibleTagline: string;
  chromeStatusTitle: string;
  chromeStatusLabel: string;
};

export type HostChromeSemantics = {
  ariaLabel: string;
  statusSummary: string | undefined;
  kernelHealth: string;
  kernelConnected: "true" | "false";
  kernelAlert: "true" | "false";
  runtimeMaintenance: string;
  shellPrivilege: string;
  privilegeSeverity: string;
  runtimeState: string;
  runtimeSeverity: string;
};

export type HostChromeViewModel = HostChromePresentation & {
  semantics: HostChromeSemantics;
};

export function deriveFallbackKernelStatus(appTagline: string): HostKernelStatus {
  const privilege = appTagline.includes("· root")
    ? "root"
    : appTagline.includes("· user")
      ? "user"
      : "unknown";
  const health = appTagline.includes("· offline")
    ? "offline"
    : appTagline.includes("· attention")
      ? "attention"
      : appTagline.includes("· healthy")
        ? "healthy"
        : "unknown";
  const maintenance = appTagline.endsWith("· maintenance")
    ? "maintenance"
    : appTagline.endsWith("· live")
      ? "live"
      : "unknown";
  const runtimeState =
    maintenance === "maintenance"
      ? "maintenance"
      : health === "offline"
        ? "offline"
        : health === "attention"
          ? "attention"
          : "healthy";
  const runtimeSeverity =
    maintenance === "maintenance"
      ? "warning"
      : health === "offline"
        ? "critical"
        : health === "attention"
          ? "warning"
          : "normal";
  const privilegeSeverity =
    privilege === "root"
      ? "elevated"
      : privilege === "user"
        ? "restricted"
        : "unknown";

  return {
    privilege,
    health,
    maintenance,
    runtimeState,
    runtimeSeverity,
    privilegeSeverity,
    connected: health !== "offline",
    alert: health === "attention" || maintenance === "maintenance",
    summary: [
      privilege !== "unknown" ? `privilege ${privilege}` : null,
      health !== "unknown" ? `kernel ${health}` : null,
      maintenance !== "unknown" ? `runtime ${maintenance}` : null,
    ].filter(Boolean).join(" · "),
  };
}

export function createHostKernelStatus(input: {
  privilege: "root" | "user";
  health: "healthy" | "attention" | "offline";
  maintenance: "maintenance" | "live";
}): HostKernelStatus {
  const runtimeState =
    input.maintenance === "maintenance"
      ? "maintenance"
      : input.health;
  const runtimeSeverity =
    input.maintenance === "maintenance"
      ? "warning"
      : input.health === "offline"
        ? "critical"
        : input.health === "attention"
          ? "warning"
          : "normal";

  return {
    privilege: input.privilege,
    health: input.health,
    maintenance: input.maintenance,
    runtimeState,
    runtimeSeverity,
    privilegeSeverity: input.privilege === "root" ? "elevated" : "restricted",
    connected: input.health !== "offline",
    alert: input.maintenance === "maintenance" || input.health === "attention",
    summary: [
      `privilege ${input.privilege}`,
      `kernel ${input.health}`,
      `runtime ${input.maintenance}`,
    ].join(" · "),
  };
}

export function formatHostChromeTagline(appName: string, status: HostKernelStatus): string {
  return `${appName} universal execution kernel · engineering shell · ${status.privilege} · ${status.health} · ${status.maintenance}`;
}

export function deriveHostChromePresentation(
  status: HostKernelStatus,
  appName: string,
): HostChromePresentation {
  const healthBadge = status.health === "offline"
    ? { label: "offline", className: "border-slate-400/80 bg-slate-100 text-slate-700" }
    : status.health === "attention"
      ? { label: "attention", className: "border-rose-300/80 bg-rose-50 text-rose-700" }
      : status.health === "healthy"
        ? { label: "healthy", className: "border-emerald-300/80 bg-emerald-50 text-emerald-700" }
        : null;
  const maintenanceBadge = status.maintenance === "maintenance"
    ? { label: "maintenance", className: "border-amber-300/80 bg-amber-50 text-amber-700" }
    : status.maintenance === "live"
      ? { label: "live", className: "border-slate-300/80 bg-slate-50 text-slate-700" }
      : null;
  const privilegeBadge = status.privilege === "root"
    ? { label: "root", className: "border-emerald-300/80 bg-emerald-50 text-emerald-700" }
    : status.privilege === "user"
      ? { label: "user", className: "border-amber-300/80 bg-amber-50 text-amber-700" }
      : null;
  const healthDotClass = maintenanceBadge?.label === "maintenance"
    ? "bg-amber-500 shadow-[0_0_0_3px_rgba(245,158,11,0.18)]"
    : healthBadge?.label === "offline"
      ? "bg-slate-500 shadow-[0_0_0_3px_rgba(100,116,139,0.18)]"
      : healthBadge?.label === "attention"
        ? "bg-rose-500 shadow-[0_0_0_3px_rgba(244,63,94,0.18)]"
        : "bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.16)]";
  const chromeCapsuleClass = maintenanceBadge?.label === "maintenance"
    ? "border-amber-200/90 bg-amber-50/90 text-amber-800"
    : healthBadge?.label === "offline"
      ? "border-slate-300/90 bg-slate-100/95 text-slate-700"
      : healthBadge?.label === "attention"
        ? "border-rose-200/90 bg-rose-50/90 text-rose-800"
        : "border-slate-200/70 bg-white/75 text-slate-500";
  const chromeCapsuleMotionClass = maintenanceBadge?.label === "maintenance"
    ? "shadow-[0_0_0_1px_rgba(245,158,11,0.10),0_10px_28px_rgba(245,158,11,0.12)]"
    : healthBadge?.label === "offline"
      ? "shadow-[0_0_0_1px_rgba(100,116,139,0.10),0_10px_24px_rgba(100,116,139,0.12)]"
      : healthBadge?.label === "attention"
        ? "shadow-[0_0_0_1px_rgba(244,63,94,0.10),0_10px_28px_rgba(244,63,94,0.14)] animate-pulse"
        : "shadow-sm";
  const chromeStatusLabel = [
    healthBadge?.label,
    maintenanceBadge?.label === "maintenance" ? "maintenance" : null,
  ].filter(Boolean).join(" / ");
  const appTagline = formatHostChromeTagline(appName, status);
  const visibleTagline = privilegeBadge || healthBadge || maintenanceBadge
    ? appTagline.replace(/\s*·\s*(root|user)\s*/g, " · ").replace(/\s*·\s*(healthy|attention|offline)\s*/g, " · ").replace(/\s*·\s*(maintenance|live)\s*$/, "").replace(/\s*·\s*$/, "")
    : appTagline;
  const chromeStatusTitle = status.summary;

  return {
    healthBadge,
    maintenanceBadge,
    privilegeBadge,
    healthDotClass,
    chromeCapsuleClass,
    chromeCapsuleMotionClass,
    visibleTagline,
    chromeStatusTitle,
    chromeStatusLabel,
  };
}

export function deriveHostChromeSemantics(
  appName: string,
  status: HostKernelStatus,
): HostChromeSemantics {
  return {
    ariaLabel: status.summary || `${appName} kernel status`,
    statusSummary: status.summary || undefined,
    kernelHealth: status.health,
    kernelConnected: status.connected ? "true" : "false",
    kernelAlert: status.alert ? "true" : "false",
    runtimeMaintenance: status.maintenance,
    shellPrivilege: status.privilege,
    privilegeSeverity: status.privilegeSeverity,
    runtimeState: status.runtimeState,
    runtimeSeverity: status.runtimeSeverity,
  };
}

export function deriveHostChromeViewModel(input: {
  appName: string;
  status: HostKernelStatus;
}): HostChromeViewModel {
  return {
    ...deriveHostChromePresentation(input.status, input.appName),
    semantics: deriveHostChromeSemantics(input.appName, input.status),
  };
}
