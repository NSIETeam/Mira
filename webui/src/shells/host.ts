import type { SettingsSectionKey } from "@/components/settings/SettingsView";
import type { KernelManifestPayload, ShellDescriptorPayload } from "@/lib/types";

export const SIDEBAR_STORAGE_KEY = "mira-webui.sidebar";
export const SESSION_UPDATES_STORAGE_KEY = "mira-webui.sidebar.session-updates.v1";
export const SHELL_SELECTION_STORAGE_KEY = "mira-webui.shell-selection.v1";
export const RESTART_STARTED_KEY = "mira-webui.restartStartedAt";
export const RESTART_ROUTE_KEY = "mira-webui.restartRoute";
export const RESTART_ROUTE_TTL_MS = 5 * 60 * 1000;
export const SIDEBAR_WIDTH = 272;
export const SIDEBAR_RAIL_WIDTH = 56;
export const MOBILE_SIDEBAR_WIDTH = `min(${SIDEBAR_WIDTH}px, calc(100vw - 0.75rem))`;

export type ShellView = "chat" | "settings" | "apps" | "automations" | "skills";
export type ShellRoute = {
  view: ShellView;
  activeKey: string | null;
  settingsSection: SettingsSectionKey;
};

const SETTINGS_SECTION_KEYS: SettingsSectionKey[] = [
  "overview",
  "appearance",
  "models",
  "image",
  "voice",
  "browser",
  "channels",
  "apps",
  "automations",
  "skills",
  "runtime",
  "advanced",
];

function isSettingsSectionKey(value: string | null): value is SettingsSectionKey {
  return SETTINGS_SECTION_KEYS.includes(value as SettingsSectionKey);
}

function readExecutionKey(params: URLSearchParams): string | null {
  return params.get("execution")?.trim() || null;
}

export function loadSelectedShellRegistryName(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(SHELL_SELECTION_STORAGE_KEY)?.trim() ?? "";
  } catch {
    return "";
  }
}

export function saveSelectedShellRegistryName(registryName: string): void {
  if (typeof window === "undefined") return;
  try {
    const normalized = registryName.trim();
    if (normalized) {
      window.localStorage.setItem(SHELL_SELECTION_STORAGE_KEY, normalized);
    } else {
      window.localStorage.removeItem(SHELL_SELECTION_STORAGE_KEY);
    }
  } catch {
    // ignore storage errors
  }
}

export function resolveSelectedShell(
  kernelManifest: KernelManifestPayload | null | undefined,
  fallbackShell: ShellDescriptorPayload | null,
): ShellDescriptorPayload | null {
  if (!kernelManifest) return fallbackShell;
  const selectedRegistryName = loadSelectedShellRegistryName();
  if (selectedRegistryName) {
    const selected = kernelManifest.shell_registry.find(
      (item) => item.registry_name === selectedRegistryName,
    );
    if (selected) return selected;
  }
  return kernelManifest.shell ?? fallbackShell;
}

export function defaultShellRoute(): ShellRoute {
  return { view: "chat", activeKey: null, settingsSection: "overview" };
}

export function shellViewForSettingsSection(section: SettingsSectionKey): ShellView {
  if (section === "apps" || section === "automations" || section === "skills") return section;
  return "settings";
}

function fallbackRestartHash(hash: string): boolean {
  return !hash || hash === "/" || hash === "/new";
}

export function rememberRestartRoute(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(RESTART_ROUTE_KEY, window.location.hash || "#/new");
  } catch {
    // ignore storage errors
  }
}

function maybeRestoreRestartHash(hash: string): string {
  if (typeof window === "undefined" || !fallbackRestartHash(hash)) return hash;
  try {
    const startedAt = Number(window.localStorage.getItem(RESTART_STARTED_KEY) ?? "0");
    const storedHash = window.localStorage.getItem(RESTART_ROUTE_KEY);
    if (!startedAt || !storedHash || Date.now() - startedAt > RESTART_ROUTE_TTL_MS) {
      window.localStorage.removeItem(RESTART_ROUTE_KEY);
      return hash;
    }
    window.localStorage.removeItem(RESTART_ROUTE_KEY);
    const nextHash = storedHash.startsWith("#") ? storedHash : `#${storedHash}`;
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${window.location.search}${nextHash}`,
    );
    return nextHash.slice(1);
  } catch {
    return hash;
  }
}

export function readShellRoute(): ShellRoute {
  if (typeof window === "undefined") return defaultShellRoute();
  const currentHash = window.location.hash.startsWith("#")
    ? window.location.hash.slice(1)
    : window.location.hash;
  const hash = maybeRestoreRestartHash(currentHash);
  if (!hash || hash === "/" || hash === "/new") return defaultShellRoute();

  const [path, query = ""] = hash.split("?", 2);
  const params = new URLSearchParams(query);
  const rawSettingsSection = params.get("section");
  const settingsSection = isSettingsSectionKey(rawSettingsSection)
    ? rawSettingsSection
    : "overview";
  const activeKey = readExecutionKey(params);

  if (path === "/settings") {
    return {
      view: shellViewForSettingsSection(settingsSection),
      activeKey,
      settingsSection,
    };
  }
  if (path === "/apps") {
    return { view: "apps", activeKey, settingsSection: "apps" };
  }
  if (path === "/automations") {
    return { view: "automations", activeKey, settingsSection: "automations" };
  }
  if (path === "/skills") {
    return { view: "skills", activeKey, settingsSection: "skills" };
  }
  if (path.startsWith("/workbench/")) {
    const encoded = path.slice("/workbench/".length);
    try {
      const key = decodeURIComponent(encoded).trim();
      return key
        ? { view: "chat", activeKey: key, settingsSection: "overview" }
        : defaultShellRoute();
    } catch {
      return defaultShellRoute();
    }
  }
  return defaultShellRoute();
}

function shellRouteHash(route: ShellRoute): string {
  if (route.view === "chat") {
    return route.activeKey
      ? `#/workbench/${encodeURIComponent(route.activeKey)}`
      : "#/new";
  }
  const params = new URLSearchParams();
  if (route.activeKey) params.set("execution", route.activeKey);
  if (route.view === "settings" && route.settingsSection !== "overview") {
    params.set("section", route.settingsSection);
  }
  const query = params.toString();
  return `#/${route.view}${query ? `?${query}` : ""}`;
}

export function writeShellRoute(route: ShellRoute, replace = false): void {
  if (typeof window === "undefined") return;
  const nextHash = shellRouteHash(route);
  if (window.location.hash === nextHash) return;
  if (replace) {
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${window.location.search}${nextHash}`,
    );
    return;
  }
  window.location.hash = nextHash;
}
