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
