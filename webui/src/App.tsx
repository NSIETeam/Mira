import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Moon, Sun } from "lucide-react";
import { useTranslation } from "react-i18next";
import { WorkbenchSidebar } from "@/components/Sidebar";
import type { SettingsSectionKey } from "@/components/settings/SettingsView";
import { WorkbenchShell } from "@/components/thread/ThreadShell";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";

import { useExecutions } from "@/hooks/useExecutions";
import { useDeferredTitleRefresh } from "@/hooks/useDeferredTitleRefresh";
import { useExecutionSidebarState } from "@/hooks/useSidebarState";
import { useSkills } from "@/hooks/useSkills";
import { usePageVisibility } from "@/hooks/usePageVisibility";
import { ThemeProvider, useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";
import {
  defaultShellRoute,
  MOBILE_SIDEBAR_WIDTH,
  readShellRoute,
  RESTART_ROUTE_KEY,
  RESTART_STARTED_KEY,
  rememberRestartRoute,
  resolveSelectedShell,
  saveSelectedShellRegistryName,
  SESSION_UPDATES_STORAGE_KEY,
  SIDEBAR_RAIL_WIDTH,
  SIDEBAR_WIDTH,
  type ShellRoute,
  type ShellView,
  writeShellRoute,
} from "@/shells/host";
import {
  HostChrome,
  SurfaceLoadingFallback,
} from "@/shells/engineering/chrome";
import { EngineeringShellOverlays } from "@/shells/engineering/overlays";
import { useEngineeringChromeState } from "@/shells/engineering/useEngineeringChromeState";
import { useEngineeringOverlayState } from "@/shells/engineering/useEngineeringOverlayState";
import { useEngineeringSidebarState } from "@/shells/engineering/useEngineeringSidebarState";
import {
  normalizeWorkspaceScope,
  useExecutionWorkspaceState,
} from "@/shells/useExecutionWorkspaceState";
import { useExecutionRuntimeState } from "@/shells/useExecutionRuntimeState";
import { useExecutionSessionState } from "@/shells/useExecutionSessionState";
import { MiraKernelConsole } from "@/shells/MiraKernelConsole";
import { useShellPresentationState } from "@/shells/useShellPresentationState";
import { resolveShellRegistration } from "@/shells/registry";
import { useKernelConsoleState } from "@/shells/useKernelConsoleState";
import { useKernelControlState } from "@/shells/useKernelControlState";
import { useKernelOperatorActions } from "@/shells/useKernelOperatorActions";
import { useShellUtilityState } from "@/shells/useShellUtilityState";
import {
  BootstrapAuthRequiredError,
  clearSavedSecret,
  consumeUrlBootstrapSecret,
  deriveWsUrl,
  fetchBootstrap,
  loadSavedSecret,
  saveSecret,
} from "@/lib/bootstrap";
import { displayTitle } from "@/lib/chat-groups";
import { deriveTitle } from "@/lib/format";
import { miraClient } from "@/lib/mira-client";
import { ClientProvider, useClient } from "@/providers/ClientProvider";
import type {
  BootstrapResponse,
  ExecutionSummary,
  KernelGuiSurface,
  KernelManifestPayload,
  RuntimeSurface,
  ShellDescriptorPayload,
  SettingsPayload,
} from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  executeKernelOperatorCommand,
  fetchKernelState,
  fetchSettings,
  updateSettings,
} from "@/lib/api";
import {
  createKernelHost,
  toKernelGuiSurface,
} from "@/lib/runtime";

type BootState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "auth"; failed?: boolean }
  | {
      status: "ready";
      client: miraClient;
      token: string;
      tokenExpiresAt: number;
      modelName: string | null;
      ingressLimits: BootstrapResponse["limits"] | null;
      guiSurface: KernelGuiSurface;
      kernel: KernelManifestPayload | null;
      shell: ShellDescriptorPayload | null;
    };

const TOKEN_REFRESH_MARGIN_MS = 30_000;
const TOKEN_REFRESH_MIN_DELAY_MS = 5_000;
const loadSettingsView = () => import("@/components/settings/SettingsView");
const SettingsView = lazy(async () => {
  const module = await loadSettingsView();
  return { default: module.SettingsView };
});
const WorkbenchSearchDialog = lazy(async () => {
  const module = await import("@/components/ExecutionSearchDialog");
  return { default: module.WorkbenchSearchDialog };
});

function bootstrapTokenExpiresAt(expiresInSeconds: number): number {
  return Date.now() + Math.max(0, expiresInSeconds) * 1000;
}

function tokenRefreshDelayMs(expiresAt: number): number {
  const remaining = Math.max(0, expiresAt - Date.now());
  const margin = Math.min(
    TOKEN_REFRESH_MARGIN_MS,
    Math.max(1_000, remaining / 2),
  );
  return Math.max(TOKEN_REFRESH_MIN_DELAY_MS, remaining - margin);
}

function AuthForm({
  failed,
  onSecret,
}: {
  failed: boolean;
  onSecret: (secret: string) => void;
}) {
  const { t } = useTranslation();
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const secret = value.trim();
    if (!secret) return;
    setSubmitting(true);
    onSecret(secret);
  };

  return (
    <div className="flex h-full w-full items-center justify-center px-6">
      <form
        onSubmit={handleSubmit}
        className="flex w-full max-w-sm flex-col gap-4"
      >
        <div className="flex flex-col items-center gap-1 text-center">
          <p className="text-lg font-semibold">{t("app.auth.title")}</p>
          <p className="text-sm text-muted-foreground">{t("app.auth.hint")}</p>
        </div>
        {failed && (
          <p className="text-center text-sm text-destructive">
            {t("app.auth.invalid")}
          </p>
        )}
        <Input
          type="password"
          placeholder={t("app.auth.placeholder")}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={submitting}
          autoFocus
        />
        <Button
          type="submit"
          className="w-full"
          disabled={!value.trim() || submitting}
        >
          {t("app.auth.submit")}
        </Button>
      </form>
    </div>
  );
}

function readSessionUpdateChatIds(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = window.localStorage.getItem(SESSION_UPDATES_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((item): item is string => typeof item === "string"));
  } catch {
    return new Set();
  }
}

function writeSessionUpdateChatIds(chatIds: Set<string>): void {
  try {
    window.localStorage.setItem(
      SESSION_UPDATES_STORAGE_KEY,
      JSON.stringify(Array.from(chatIds)),
    );
  } catch {
    // ignore storage errors (private mode, etc.)
  }
}

function isBootstrapAuthRequired(error: unknown): boolean {
  if (error instanceof BootstrapAuthRequiredError) return true;
  const msg = error instanceof Error ? error.message : String(error);
  return msg.includes("HTTP 401") || msg.includes("HTTP 403");
}

export default function App() {
  const { t } = useTranslation();
  const [state, setState] = useState<BootState>({ status: "loading" });
  const bootstrapSecretRef = useRef("");

  const refreshReadyClient = useCallback(
    async (client: miraClient, fallbackSurface: KernelGuiSurface) => {
      const boot = await fetchBootstrap("", bootstrapSecretRef.current);
      const url = deriveWsUrl(boot.ws_path, boot.token, boot.ws_url);
      const kernelManifest = boot.kernel;
      const shellDescriptor = resolveSelectedShell(kernelManifest, boot.shell ?? null);
      const runtimeCapabilities = kernelManifest?.capabilities ?? boot.runtime_capabilities;
      const guiSurface = boot.runtime_surface
        ? toKernelGuiSurface(boot.runtime_surface)
        : fallbackSurface;
      const runtimeHost = createKernelHost(guiSurface, runtimeCapabilities);
      const tokenExpiresAt = bootstrapTokenExpiresAt(boot.expires_in);
      if (runtimeHost.socketFactory) {
        client.updateUrl(url, runtimeHost.socketFactory);
      } else {
        client.updateUrl(url);
      }
      setState((current) =>
        current.status === "ready" && current.client === client
          ? {
              ...current,
              token: boot.api_token,
              tokenExpiresAt,
              modelName: boot.model_name ?? current.modelName,
              ingressLimits: boot.limits ?? current.ingressLimits,
              guiSurface,
              kernel: kernelManifest ?? current.kernel,
              shell: shellDescriptor ?? current.shell,
            }
          : current,
      );
      return { token: boot.api_token, url };
    },
    [],
  );

  const bootstrapWithSecret = useCallback(
    (secret: string) => {
      let cancelled = false;
      (async () => {
        setState({ status: "loading" });
        try {
          const boot = await fetchBootstrap("", secret);
          if (cancelled) return;
          if (secret) saveSecret(secret);
          const url = deriveWsUrl(boot.ws_path, boot.token, boot.ws_url);
          const kernelManifest = boot.kernel;
          const shellDescriptor = resolveSelectedShell(kernelManifest, boot.shell ?? null);
          const runtimeCapabilities = kernelManifest?.capabilities ?? boot.runtime_capabilities;
          const guiSurface = toKernelGuiSurface(boot.runtime_surface);
          const runtimeHost = createKernelHost(guiSurface, runtimeCapabilities);
          const client = new miraClient({
            url,
            socketFactory: runtimeHost.socketFactory,
            onReauth: async () => {
              try {
                const refreshed = await refreshReadyClient(client, guiSurface);
                return refreshed.url;
              } catch {
                return null;
              }
            },
          });
          bootstrapSecretRef.current = secret;
          client.connect();
          setState({
            status: "ready",
            client,
            token: boot.api_token,
            tokenExpiresAt: bootstrapTokenExpiresAt(boot.expires_in),
            modelName: boot.model_name ?? null,
            ingressLimits: boot.limits ?? null,
            guiSurface,
            kernel: kernelManifest ?? null,
            shell: shellDescriptor,
          });
        } catch (e) {
          if (cancelled) return;
          if (isBootstrapAuthRequired(e)) {
            setState({ status: "auth", failed: !!secret });
          } else {
            setState({
              status: "error",
              message: e instanceof Error ? e.message : String(e),
            });
          }
        }
      })();
      return () => {
        cancelled = true;
      };
    },
    [refreshReadyClient],
  );

  useEffect(() => {
    if (state.status !== "ready") return;
    const client = state.client;
    const timer = window.setTimeout(async () => {
      try {
        await refreshReadyClient(client, state.guiSurface);
      } catch (e) {
        if (isBootstrapAuthRequired(e)) {
          setState({ status: "auth", failed: !!bootstrapSecretRef.current });
        }
      }
    }, tokenRefreshDelayMs(state.tokenExpiresAt));
    return () => window.clearTimeout(timer);
  }, [refreshReadyClient, state]);

  useEffect(() => {
    const saved = consumeUrlBootstrapSecret() || loadSavedSecret();
    return bootstrapWithSecret(saved);
  }, [bootstrapWithSecret]);

  if (state.status === "loading") {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <div className="flex flex-col items-center gap-3 animate-in fade-in-0 duration-300">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-foreground/40" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-foreground/60" />
            </span>
            {t("app.loading.connecting")}
          </div>
        </div>
      </div>
    );
  }
  if (state.status === "auth") {
    return (
      <AuthForm
        failed={!!state.failed}
        onSecret={(s) => bootstrapWithSecret(s)}
      />
    );
  }
  if (state.status === "error") {
    return (
      <div className="flex h-full w-full items-center justify-center px-4 text-center">
        <div className="flex max-w-md flex-col items-center gap-3">
          <p className="text-lg font-semibold">{t("app.error.title")}</p>
          <p className="text-sm text-muted-foreground">{state.message}</p>
          <p className="text-xs text-muted-foreground">
            {t("app.error.gatewayHint")}
          </p>
        </div>
      </div>
    );
  }

  const handleModelNameChange = (modelName: string | null) => {
    setState((current) =>
      current.status === "ready" ? { ...current, modelName } : current,
    );
  };

  useEffect(() => {
    if (state.status !== "ready") return;
    if (typeof document === "undefined") return;
    const shellName = state.shell?.name || "engineering";
    const shellTheme = state.shell?.theme || "engineering";
    const shellDescription = state.shell?.description || "";
    document.title = state.shell?.display_name || "Mira";
    document.documentElement.dataset.shellName = shellName;
    document.documentElement.dataset.shellTheme = shellTheme;
    document.documentElement.dataset.shellDescription = shellDescription;
    document.documentElement.classList.toggle("shell-engineering", shellTheme === "engineering");
  }, [state]);

  const handleLogout = () => {
    if (state.status === "ready") {
      state.client.close();
    }
    clearSavedSecret();
    setState({ status: "auth" });
  };

  const handleNativeEngineRestart = async (): Promise<string> => {
    const runtimeHost = createKernelHost(state.guiSurface);
    if (!runtimeHost.restartEngine) {
      throw new Error("native engine restart is unavailable");
    }
    rememberRestartRoute();
    try {
      window.localStorage.setItem(RESTART_STARTED_KEY, String(Date.now()));
    } catch {
      // ignore storage errors
    }
    try {
      await runtimeHost.restartEngine();
      const refreshed = await refreshReadyClient(state.client, state.guiSurface);
      return refreshed.token;
    } finally {
      try {
        window.localStorage.removeItem(RESTART_STARTED_KEY);
        window.localStorage.removeItem(RESTART_ROUTE_KEY);
      } catch {
        // ignore storage errors
      }
    }
  };

  return (
    <ClientProvider
      client={state.client}
      token={state.token}
      modelName={state.modelName}
      ingressLimits={state.ingressLimits}
    >
      <Shell
        runtimeSurface={state.guiSurface}
        kernelManifest={state.kernel}
        shellDescriptor={state.shell}
        onSettingsPayloadChange={(payload) => {
          setState((current) => {
            if (current.status !== "ready" || !payload.kernel) return current;
            return {
              ...current,
              kernel: payload.kernel,
              shell: payload.kernel.shell,
            };
          });
        }}
        onSelectProfile={async (registryName) => {
          const payload = await updateSettings(state.token, { profileName: registryName });
          if (payload.kernel) {
            setState((current) => {
              if (current.status !== "ready") return current;
              const nextKernel = payload.kernel ?? current.kernel;
              const nextShell = nextKernel?.shell ?? current.shell;
              return {
                ...current,
                shell: nextShell,
                kernel: nextKernel,
              };
            });
          }
        }}
        onSelectShell={async (registryName) => {
          const payload = await updateSettings(state.token, { shellName: registryName });
          saveSelectedShellRegistryName(registryName);
          if (payload.kernel) {
            setState((current) => {
              if (current.status !== "ready") return current;
              const nextKernel = payload.kernel ?? current.kernel;
              const nextShell = nextKernel?.shell ?? current.shell;
              return {
                ...current,
                shell: nextShell,
                kernel: nextKernel,
              };
            });
          }
        }}
        onModelNameChange={handleModelNameChange}
        onLogout={handleLogout}
        onNativeEngineRestart={handleNativeEngineRestart}
        onKernelChange={(kernel) => {
          setState((current) => {
            if (current.status !== "ready") return current;
            return {
              ...current,
              kernel,
              shell: kernel.shell,
            };
          });
        }}
      />
    </ClientProvider>
  );
}

function Shell({
  runtimeSurface,
  kernelManifest,
  shellDescriptor,
  onSettingsPayloadChange,
  onSelectProfile,
  onSelectShell,
  onModelNameChange,
  onLogout,
  onNativeEngineRestart,
  onKernelChange,
}: {
  runtimeSurface: RuntimeSurface;
  kernelManifest: KernelManifestPayload | null;
  shellDescriptor: ShellDescriptorPayload | null;
  onSettingsPayloadChange: (payload: SettingsPayload) => void;
  onSelectProfile: (registryName: string) => Promise<void>;
  onSelectShell: (registryName: string) => Promise<void>;
  onModelNameChange: (modelName: string | null) => void;
  onLogout: () => void;
  onNativeEngineRestart: () => Promise<string>;
  onKernelChange: (kernel: KernelManifestPayload) => void;
}) {
  const { t } = useTranslation();
  const { client, token } = useClient();
  const { theme, toggle } = useTheme();
  const {
    sessions,
    executions,
    loading,
    refresh,
    createExecution,
    forkExecution,
    deleteExecution,
    getExecutionAutomations,
  } = useExecutions();
  const { state: sidebarState, update: updateSidebarState } =
    useExecutionSidebarState(executions, !loading);
  const executionSummaries = executions as ExecutionSummary[];
  const initialRouteRef = useRef<ShellRoute | null>(null);
  if (!initialRouteRef.current) initialRouteRef.current = readShellRoute();
  const [activeKey, setActiveKey] = useState<string | null>(
    initialRouteRef.current.activeKey,
  );
  const [view, setView] = useState<ShellView>(initialRouteRef.current.view);
  const [settingsInitialSection, setSettingsInitialSection] =
    useState<SettingsSectionKey>(initialRouteRef.current.settingsSection);
  const [updatedExecutionIds, setUpdatedExecutionIds] = useState<Set<string>>(readSessionUpdateChatIds);
  const skills = useSkills(token);
  const pageVisible = usePageVisibility();
  const [settingsSnapshot, setSettingsSnapshot] = useState<SettingsPayload | null>(null);
  const activeExecutionIdRef = useRef<string | null>(null);
  const effectiveRuntimeSurface =
    settingsSnapshot?.surface ?? settingsSnapshot?.runtime_surface ?? runtimeSurface;
  const showHostChrome = effectiveRuntimeSurface === "native";
  const appName = kernelManifest?.identity?.app_name ?? "Mira";
  const shellSupportsThreads = shellDescriptor?.supports_threads ?? true;
  const shellSupportsRuntimeControls = shellDescriptor?.supports_runtime_controls ?? true;
  const shellSupportsFileActivity = shellDescriptor?.supports_file_activity ?? true;
  const shellCapabilities = useMemo(() => ({
    supportsThreads: shellSupportsThreads,
    supportsRuntimeControls: shellSupportsRuntimeControls,
    supportsFileActivity: shellSupportsFileActivity,
  }), [shellSupportsFileActivity, shellSupportsRuntimeControls, shellSupportsThreads]);
  const shellTitle = shellDescriptor?.display_name ?? appName;
  const shellRegistration = useMemo(
    () => resolveShellRegistration(shellDescriptor),
    [shellDescriptor],
  );
  const ShellView = shellRegistration.component;
  const shellHostContract = shellRegistration.hostContract;
  const shellUtilitySurfaceEnabled = shellHostContract.surfaces.allowUtilitySurface;
  const shellExecutionForkEnabled = shellHostContract.actions.allowExecutionFork;
  const shellWorkspaceControlsEnabled = shellHostContract.surfaces.allowWorkspaceControls;
  const shellRuntimeModelControlsEnabled = shellHostContract.surfaces.allowRuntimeModelControls;
  const shellKernelConsoleEnabled = shellHostContract.surfaces.allowKernelConsole;
  const shellComposerEnabled = shellHostContract.composer.allowComposer;
  const shellExecutionReadOnly = shellHostContract.composer.readOnlyExecution;
  const activeShellView = shellUtilitySurfaceEnabled ? view : "chat";
  const showMainSidebar =
    shellHostContract.chrome.showSidebarChrome
    && shellSupportsThreads
    && activeShellView !== "settings";
  const {
    hostSidebarOpen,
    hostSidebarPreviewOpen,
    mobileSidebarOpen,
    sessionSearchOpen,
    setMobileSidebarOpen,
    setSessionSearchOpen,
    openHostSidebarPreview,
    scheduleHostSidebarPreviewClose,
    closeHostSidebar,
    openHostSidebar,
    toggleHostSidebar,
    closeMobileSidebar,
    toggleSidebar,
  } = useEngineeringChromeState({
    showHostChrome,
    showMainSidebar,
  });

  const navigate = useCallback(
    (route: ShellRoute, options?: { replace?: boolean }) => {
      setActiveKey(route.activeKey);
      setView(route.view);
      setSettingsInitialSection(route.settingsSection);
      writeShellRoute(route, options?.replace);
    },
    [],
  );

  useEffect(() => {
    const applyRoute = () => {
      const route = readShellRoute();
      setActiveKey(route.activeKey);
      setView(route.view);
      setSettingsInitialSection(route.settingsSection);
      setWorkspaceError(null);
    };
    window.addEventListener("hashchange", applyRoute);
    return () => window.removeEventListener("hashchange", applyRoute);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchSettings(token)
      .then((payload) => {
        if (!cancelled) {
          setSettingsSnapshot(payload);
          onSettingsPayloadChange(payload);
        }
      })
      .catch(() => {
        if (!cancelled) setSettingsSnapshot(null);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    writeSessionUpdateChatIds(updatedExecutionIds);
  }, [updatedExecutionIds]);

  const {
    pendingDelete,
    setPendingDelete,
    pendingRename,
    setPendingRename,
    pendingProjectRename,
    setPendingProjectRename,
    visiblePairingRequests,
    pairingBusyCode,
    pairingError,
    onRequestRename,
    onConfirmRename,
    onRequestRenameProject,
    onConfirmProjectRename,
    onConfirmDelete,
    onRequestDelete,
    onPairingAction,
    onDismissPairingRequest,
    onToggleArchive,
  } = useEngineeringOverlayState({
    token,
    pageVisible,
    activeKey,
    sessions,
    archivedKeys: sidebarState.archived_keys,
    updateSidebarState,
    navigate,
    getExecutionAutomations,
    deleteExecution,
  });

  const activeSession = useMemo<ExecutionSummary | null>(() => {
    if (!activeKey) return null;
    return executionSummaries.find((s) => s.key === activeKey) ?? null;
  }, [executionSummaries, activeKey]);
  const activeExecutionId = activeSession?.chatId ?? null;
  const activeExecution = activeSession;
  const {
    runningExecutionIds,
    isRestarting,
    restartToast,
    onRestart,
  } = useExecutionRuntimeState({
    client,
    loading,
    sessions,
    activeSessionChatId: activeSession?.chatId ?? null,
    activeExecutionIdRef,
    setUpdatedExecutionIds,
    formatRestartCompleted: (seconds) =>
      t("app.restart.completed", { seconds }),
  });
  const { connectionStatus, runtimeModel, recentErrors } = useKernelConsoleState(client);
  const appTagline = `${kernelManifest?.identity?.app_name ?? "Mira"} execution kernel`;
  const kernelControl = useKernelControlState({
    kernelManifest,
    token,
    onKernelUpdate: onKernelChange,
  });
  const { byId: operatorActionMap } = useKernelOperatorActions({
    actionRegistry: kernelManifest?.operator_console.action_registry ?? [],
    handlers: {
      open_kernel_settings: () => onOpenSettings("runtime"),
      restart_runtime: onRestart,
      restart_engine: () => {
        void onNativeEngineRestart();
      },
      inspect_faults: () => kernelControl.setSelectedPane("faults"),
      record_fault: () => {
        void kernelControl.recordFault();
      },
      clear_fault: () => {
        void kernelControl.clearFault();
      },
      restart_bridge: () => {
        void kernelControl.restartBridge();
      },
      pause_runtime: () => {
        void kernelControl.pauseRuntime();
      },
      resume_runtime: () => {
        void kernelControl.resumeRuntime();
      },
      degrade_runtime: () => {
        void kernelControl.degradeRuntime();
      },
      drain_background: () => {
        void kernelControl.drainBackground();
      },
      prioritize_goal_lane: () => {
        void kernelControl.prioritizeGoalLane();
      },
      enter_maintenance: () => {
        void kernelControl.enterMaintenance();
      },
      exit_maintenance: () => {
        void kernelControl.exitMaintenance();
      },
      inspect_modules: () => kernelControl.setSelectedPane("modules"),
      switch_adapter: () => {
        kernelControl.setSelectedPane("adapters");
        void kernelControl.cycleAdapter();
      },
      attach_board: () => {
        void kernelControl.attachBoard();
      },
    },
  });
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    const syncKernel = async () => {
      try {
        const payload = await fetchKernelState(token);
        if (cancelled) return;
        onKernelChange(payload.kernel);
      } catch {
        // keep the current shell state; operator actions still refresh on demand
      }
    };
    void syncKernel();
    const timer = window.setInterval(() => {
      void syncKernel();
    }, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [token]);
  const runningExecutionIdList = useMemo(() => Array.from(runningExecutionIds), [runningExecutionIds]);
  const updatedExecutionIdList = useMemo(() => Array.from(updatedExecutionIds), [updatedExecutionIds]);
  const activeExecutionRunning = activeExecutionId ? runningExecutionIds.has(activeExecutionId) : false;
  const onWorkspaceScopeRejected = t("errors.workspaceScopeRejected.body");
  const onNewExecution = useCallback(() => {
    navigate(defaultShellRoute());
    setDraftWorkspaceScope(null);
    setWorkspaceError(null);
    setSessionSearchOpen(false);
    setMobileSidebarOpen(false);
  }, [navigate, setMobileSidebarOpen, setSessionSearchOpen]);
  const {
    workspaces,
    workspaceError,
    activeWorkspaceScope,
    refreshWorkspaces,
    applyWorkspaceScope,
    onCreateExecution,
    onNewExecutionInProject,
    setWorkspaceError,
    setDraftWorkspaceScope,
    setWorkspaceOverrides,
  } = useExecutionWorkspaceState({
    token,
    activeExecutionId,
    activeExecution,
    activeExecutionRunning,
    createExecution,
    navigate,
    setMobileSidebarOpen,
    client,
    onNewExecution,
    onWorkspaceScopeRejected,
  });
  const executionSearchOpen =
    shellHostContract.chrome.showSearchDialog ? sessionSearchOpen : false;
  useExecutionSessionState({
    client,
    loading,
    activeKey,
    activeExecutionId,
    activeExecutionIdRef,
    sessions,
    executionSummaries,
    navigate,
    setUpdatedExecutionIds,
    setWorkspaceOverrides,
    setDraftWorkspaceScope,
    setWorkspaceError,
    normalizeWorkspaceScope,
    refreshWorkspaces,
  });

  useEffect(() => {
    return client.onError((error) => {
      if (error.kind !== "workspace_scope_rejected") return;
      setWorkspaceError(t("errors.workspaceScopeRejected.body"));
      void refreshWorkspaces();
    });
  }, [client, refreshWorkspaces, t]);

  const onForkExecution = useCallback(async (
    sourceChatId: string,
    beforeUserIndex: number,
  ) => {
    try {
      const sourceSession = sessions.find((session) => session.chatId === sourceChatId);
      const sourceTitle = sourceSession
        ? displayTitle(sourceSession, sidebarState.title_overrides, t("chat.newChat"))
        : t("chat.newChat");
      const executionId = await forkExecution(
        sourceChatId,
        beforeUserIndex,
        t("chat.forkTitle", { title: sourceTitle }),
      );
      navigate({
        view: "chat",
        activeKey: `websocket:${executionId}`,
        settingsSection: "overview",
      });
      setMobileSidebarOpen(false);
      return executionId;
    } catch (e) {
      console.error("Failed to fork execution", e);
      return null;
    }
  }, [forkExecution, navigate, sessions, sidebarState.title_overrides, t]);

  const onOpenSessionSearch = useCallback(() => {
    setMobileSidebarOpen(false);
    setSessionSearchOpen(true);
  }, [setMobileSidebarOpen, setSessionSearchOpen]);

  const {
    onOpenSettings,
    onSettingsIntent,
    onOpenModelSettings,
    onOpenApps,
    onOpenAutomations,
    onOpenSkills,
    onSettingsSectionChange,
    onBackToChat,
  } = useShellUtilityState({
    activeKey,
    sessions,
    shellAllowsUtilitySurface: shellUtilitySurfaceEnabled,
    navigate,
    setSessionSearchOpen,
    setMobileSidebarOpen,
    preloadSettingsView: () => {
      void loadSettingsView();
    },
  });

  useEffect(() => {
    return client.onRuntimeModelUpdate((modelName) => {
      onModelNameChange(modelName);
    });
  }, [client, onModelNameChange]);

  const onTurnEnd = useDeferredTitleRefresh(activeSession, refresh);

  const headerTitle = shellSupportsThreads
    ? activeSession
      ? sidebarState.title_overrides[activeSession.key] ||
        activeSession.title ||
        deriveTitle(activeSession.preview, t("chat.newChat"))
      : appName
    : shellTitle;
  useShellPresentationState({
    activeSession,
    activeShellView,
    shellSupportsThreads,
    shellTitle,
    headerTitle,
    settingsTitle: t("settings.sidebar.title"),
    appsTitle: t("settings.nav.apps", { defaultValue: "Apps" }),
    automationsTitle: t("settings.nav.automations", { defaultValue: "Automations" }),
    skillsTitle: t("settings.nav.skills", { defaultValue: "Skills" }),
    baseTitle: appName,
    formatChatTitle: (title) => t("app.documentTitle.chat", { title }),
    showHostChrome,
    onNewExecution,
    onOpenSessionSearch,
  });

  const { onSelectExecution, sidebarProps } = useEngineeringSidebarState({
    sessions,
    executions,
    activeKey,
    loading,
    activeShellView,
    sidebarState,
    updateSidebarState,
    navigate,
    setUpdatedExecutionIds,
    setDraftWorkspaceScope,
    setWorkspaceError,
    setMobileSidebarOpen,
    normalizeWorkspaceScope,
    onNewExecution,
    onRequestDelete,
    onRequestRename,
    onToggleArchive,
    onRequestRenameProject,
    onNewExecutionInProject,
    onOpenSettings,
    onOpenApps,
    onOpenAutomations,
    onOpenSkills,
    onSettingsIntent,
    onOpenSessionSearch,
    runningExecutionIdList,
    updatedExecutionIdList,
    defaultWorkspacePath: workspaces?.default_scope.project_path ?? null,
  });
  const onSelectSearchResult = useCallback(
    (key: string) => {
      setSessionSearchOpen(false);
      onSelectExecution(key);
    },
    [onSelectExecution],
  );
  const hostSidebarCollapsed = showHostChrome && !hostSidebarOpen;
  const showHostSidebarPreview =
    showMainSidebar && hostSidebarCollapsed && hostSidebarPreviewOpen;
  const hostSidebarFlowWidth = showHostChrome
    ? (hostSidebarOpen ? SIDEBAR_WIDTH : 0)
    : (hostSidebarOpen ? SIDEBAR_WIDTH : SIDEBAR_RAIL_WIDTH);
  const renderHostSidebarFlowContent = !showHostChrome || hostSidebarOpen;

  return (
    <ThemeProvider theme={theme}>
      <ShellView
        showHostChrome={showHostChrome}
        shellDescriptor={shellDescriptor}
        shellTitle={shellTitle}
        shellCapabilities={shellCapabilities}
        hostContract={shellHostContract}
        topChrome={showHostChrome ? (
          <HostChrome
            appName={appName}
            appTagline={appTagline}
            onToggleSidebar={showMainSidebar ? toggleHostSidebar : undefined}
            onSidebarPreviewEnter={openHostSidebarPreview}
            onSidebarPreviewLeave={scheduleHostSidebarPreviewClose}
            sidebarOpen={hostSidebarOpen}
            rightAction={
              view === "chat" ? undefined : (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={t("thread.header.toggleTheme")}
                  onClick={toggle}
                  className="h-8 w-8 rounded-full text-muted-foreground/85 hover:bg-accent/40 hover:text-foreground"
                >
                  {theme === "dark" ? (
                    <Sun className="h-4 w-4" />
                  ) : (
                    <Moon className="h-4 w-4" />
                  )}
                </Button>
              )
            }
          />
        ) : null}
        hostSidebarFlow={showMainSidebar ? (
          <aside
            data-testid="host-sidebar-flow"
            className={cn(
              "relative z-20 hidden shrink-0 overflow-hidden lg:block",
              "transition-[width] duration-300 ease-out",
            )}
            style={{
              width: hostSidebarFlowWidth,
            }}
          >
            {renderHostSidebarFlowContent ? (
              <div
                className={cn(
                  "absolute inset-y-0 left-0 h-full w-full overflow-hidden",
                  showHostChrome
                    ? "host-sidebar-glass"
                    : "bg-sidebar",
                )}
              >
                <WorkbenchSidebar
                  {...sidebarProps}
                  appName={appName}
                  appTagline={appTagline}
                  collapsed={!showHostChrome && !hostSidebarOpen}
                  hostChromeInset={showHostChrome}
                  onCollapse={closeHostSidebar}
                  onExpand={openHostSidebar}
                />
              </div>
            ) : null}
          </aside>
        ) : null}
        hostSidebarPreview={showHostSidebarPreview ? (
          <aside
            data-testid="host-sidebar-preview"
            className="absolute inset-y-0 left-0 z-30 hidden overflow-hidden lg:block animate-in fade-in-0 slide-in-from-left-2 duration-150"
            style={{ width: SIDEBAR_WIDTH }}
            onMouseEnter={openHostSidebarPreview}
            onMouseLeave={scheduleHostSidebarPreviewClose}
          >
            <div className="h-full w-full overflow-hidden host-sidebar-glass shadow-2xl">
              <WorkbenchSidebar
                {...sidebarProps}
                appName={appName}
                appTagline={appTagline}
                hostChromeInset={showHostChrome}
                onCollapse={closeHostSidebar}
                onExpand={openHostSidebar}
              />
            </div>
          </aside>
        ) : null}
        mobileSidebar={showMainSidebar ? (
          <Sheet
            open={mobileSidebarOpen}
            onOpenChange={(open) => setMobileSidebarOpen(open)}
          >
            <SheetContent
              side="left"
              showCloseButton={false}
              aria-describedby={undefined}
              className="p-0 lg:hidden"
              style={{ width: MOBILE_SIDEBAR_WIDTH, maxWidth: MOBILE_SIDEBAR_WIDTH }}
            >
              <SheetTitle className="sr-only">{t("sidebar.navigation")}</SheetTitle>
              <WorkbenchSidebar
                {...sidebarProps}
                appName={appName}
                appTagline={appTagline}
                onCollapse={closeMobileSidebar}
                containActionMenus
              />
            </SheetContent>
          </Sheet>
        ) : null}
        searchDialog={shellSupportsThreads && executionSearchOpen ? (
          <Suspense fallback={null}>
            <WorkbenchSearchDialog
              open
              onOpenChange={setSessionSearchOpen}
              sessions={sessions}
              executions={executions}
              activeExecutionKey={activeKey}
              loading={loading}
              titleOverrides={sidebarState.title_overrides}
              onSelect={onSelectSearchResult}
              onSelectExecution={onSelectSearchResult}
            />
          </Suspense>
        ) : null}
        kernelConsole={activeShellView === "chat" && shellKernelConsoleEnabled ? (
          <MiraKernelConsole
            kernelManifest={kernelManifest}
            shellDescriptor={shellDescriptor}
            activeExecution={activeExecution}
            activeWorkspaceScope={activeWorkspaceScope}
            workspaceError={workspaceError}
            runningExecutionCount={runningExecutionIdList.length}
            connectionStatus={connectionStatus}
            runtimeModel={runtimeModel}
            recentErrors={recentErrors}
            embeddedTargetHint={
              kernelManifest?.profile.name === "mira-embedded-lab"
                ? "Embedded lab kernel profile enabled for constrained targets"
                : null
            }
            operatorActions={operatorActionMap}
            selectedPane={kernelControl.selectedPane}
            onSelectPane={kernelControl.setSelectedPane}
            selectedAdapterName={kernelControl.selectedAdapterName}
            onSelectAdapter={kernelControl.setSelectedAdapterName}
            selectedModuleName={kernelControl.selectedModuleName}
            onSelectModule={(name) => {
              void kernelControl.focusModule(name);
            }}
            selectedBoardTransport={kernelControl.selectedBoardTransport}
            onSelectBoardTransport={kernelControl.setSelectedBoardTransport}
            selectedBoardPort={kernelControl.selectedBoardPort}
            onSelectBoardPort={kernelControl.setSelectedBoardPort}
            onAttachBoard={(options) => {
              void kernelControl.attachBoard(options);
            }}
            onRunOperatorCommand={async (command) => {
              const payload = await executeKernelOperatorCommand(token, command);
              onKernelChange(payload.kernel);
              return {
                output: payload.output,
                targetPane: payload.target_pane ?? null,
                details: payload.details,
              };
            }}
          />
        ) : null}
        chatView={(
          <div
            className={cn(
              "absolute inset-0 flex flex-col",
              activeShellView !== "chat" && "hidden",
            )}
          >
            <WorkbenchShell
              execution={activeExecution}
              title={headerTitle}
              onToggleSidebar={shellSupportsThreads ? toggleSidebar : undefined}
              onNewExecution={onNewExecution}
              onCreateExecution={onCreateExecution}
              onForkExecution={shellExecutionForkEnabled ? onForkExecution : undefined}
              onTurnEnd={onTurnEnd}
              theme={theme}
              onToggleTheme={toggle}
              hideSidebarToggleForHostChrome
              hostChromeTitleInset={hostSidebarCollapsed}
              hideHeader={false}
              workspaceScope={shellWorkspaceControlsEnabled ? activeWorkspaceScope : null}
              workspaceDefaultScope={shellWorkspaceControlsEnabled ? (workspaces?.default_scope ?? null) : null}
              workspaceControls={shellWorkspaceControlsEnabled ? (workspaces?.controls ?? null) : null}
              workspaceScopeDisabled={shellWorkspaceControlsEnabled ? activeExecutionRunning : true}
              workspaceError={shellWorkspaceControlsEnabled ? workspaceError : null}
              onWorkspaceScopeChange={shellWorkspaceControlsEnabled ? applyWorkspaceScope : undefined}
              settingsSnapshot={settingsSnapshot}
              onOpenModelSettings={
                shellSupportsRuntimeControls && shellRuntimeModelControlsEnabled
                  ? onOpenModelSettings
                  : undefined
              }
              supportsThreads={shellSupportsThreads}
              supportsRuntimeControls={shellSupportsRuntimeControls}
              supportsFileActivity={shellSupportsFileActivity}
              allowComposer={shellComposerEnabled}
              readOnlyExecution={shellExecutionReadOnly}
              shellDescription={shellDescriptor?.description ?? null}
              skills={skills}
            />
          </div>
        )}
        utilityView={activeShellView !== "chat" && shellUtilitySurfaceEnabled ? (
          <div className="absolute inset-0 flex flex-col">
            {shellSupportsRuntimeControls ? (
              <Suspense fallback={<SurfaceLoadingFallback />}>
                <SettingsView
                  theme={theme}
                  initialSection={settingsInitialSection}
                  initialSettings={settingsSnapshot}
                  kernelManifest={kernelManifest}
                  onSelectProfile={onSelectProfile}
                  onSelectShell={onSelectShell}
                  showSidebar={view === "settings"}
                  onToggleTheme={toggle}
                  onBackToChat={onBackToChat}
                  onModelNameChange={onModelNameChange}
                  onSettingsChange={(payload) => {
                    setSettingsSnapshot(payload);
                    onSettingsPayloadChange(payload);
                  }}
                  skills={skills}
                  onWorkspaceSettingsChange={refreshWorkspaces}
                  onSectionChange={onSettingsSectionChange}
                  onLogout={onLogout}
                  onRestart={onRestart}
                  onNativeEngineRestart={onNativeEngineRestart}
                  isRestarting={isRestarting}
                  hostChromeInset={showHostChrome}
                />
              </Suspense>
            ) : (
              <div className="flex h-full items-center justify-center px-6 text-center">
                <div className="max-w-md space-y-3">
                  <h2 className="text-lg font-semibold">{shellTitle}</h2>
                  <p className="text-sm text-muted-foreground">
                    This shell disables runtime controls and keeps the execution layer focused on chat.
                  </p>
                </div>
              </div>
            )}
          </div>
        ) : null}
        overlays={
          <EngineeringShellOverlays
            pendingDelete={pendingDelete}
            pendingRename={pendingRename}
            pendingProjectRename={pendingProjectRename}
            restartToast={restartToast}
            visiblePairingRequests={visiblePairingRequests}
            pairingBusyCode={pairingBusyCode}
            pairingError={pairingError}
            onCancelDelete={() => setPendingDelete(null)}
            onConfirmDelete={onConfirmDelete}
            onCancelRename={() => setPendingRename(null)}
            onConfirmRename={onConfirmRename}
            onCancelProjectRename={() => setPendingProjectRename(null)}
            onConfirmProjectRename={onConfirmProjectRename}
            onApprovePairing={(code) => void onPairingAction("approve", code)}
            onDismissPairing={onDismissPairingRequest}
          />
        }
      />
    </ThemeProvider>
  );
}
