import { useMemo, useState } from "react";

import type {
  ExecutionSummary,
  KernelManifestPayload,
  KernelOperatorActionResult,
  ShellDescriptorPayload,
  WorkspaceScopePayload,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  normalizedShellHostContract,
  normalizedShellMode,
  shellAllowsPrivilegedRuntimeControls,
  shellCanElevate,
  shellPrivilegeRole,
} from "./contract";
import type { KernelOperatorActionBinding } from "./useKernelOperatorActions";
import type { KernelConsoleErrorEntry } from "./useKernelConsoleState";

function chipTone(ok: boolean): string {
  return ok
    ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
    : "border-amber-500/20 bg-amber-500/10 text-amber-700";
}

function operatorPanelTone(subject: string | null | undefined): string {
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

function formatKernelTimestamp(value: unknown): string {
  const timestamp = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(timestamp) || timestamp <= 0) return "unknown";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "unknown";
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function formatKernelTimestampList(value: string): string {
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

export function MiraKernelConsole({
  kernelManifest,
  shellDescriptor,
  activeExecution,
  activeWorkspaceScope,
  workspaceError,
  runningExecutionCount,
  connectionStatus,
  runtimeModel,
  recentErrors,
  embeddedTargetHint,
  operatorActions,
  selectedPane,
  onSelectPane,
  selectedAdapterName,
  onSelectAdapter,
  selectedModuleName,
  onSelectModule,
  selectedBoardTransport,
  onSelectBoardTransport,
  selectedBoardPort,
  onSelectBoardPort,
  onAttachBoard,
  onRunOperatorCommand,
}: {
  kernelManifest: KernelManifestPayload | null;
  shellDescriptor: ShellDescriptorPayload | null;
  activeExecution: ExecutionSummary | null;
  activeWorkspaceScope: WorkspaceScopePayload | null;
  workspaceError: string | null;
  runningExecutionCount: number;
  connectionStatus: string;
  runtimeModel: string | null;
  recentErrors: KernelConsoleErrorEntry[];
  embeddedTargetHint?: string | null;
  operatorActions?: Record<string, KernelOperatorActionBinding>;
  selectedPane: string;
  onSelectPane: (pane: string) => void;
  selectedAdapterName: string | null;
  onSelectAdapter: (name: string | null) => void;
  selectedModuleName: string | null;
  onSelectModule: (name: string | null) => void;
  selectedBoardTransport?: string | null;
  onSelectBoardTransport?: (transport: string | null) => void;
  selectedBoardPort?: string | null;
  onSelectBoardPort?: (port: string | null) => void;
  onAttachBoard?: (options?: { transport?: string | null; port?: string | null }) => void;
  onRunOperatorCommand?: (command: string) => Promise<{
    output?: string;
    targetPane?: string | null;
    details?: Record<string, string | number | boolean | null>;
    action_result?: KernelOperatorActionResult;
  } | void>;
}) {
  const appIdentity = kernelManifest?.identity?.app_name ?? "Mira";
  const shellMode = normalizedShellMode(shellDescriptor);
  const hostContract = normalizedShellHostContract(shellDescriptor);
  const privilegeRole = shellPrivilegeRole(hostContract);
  const canElevate = shellCanElevate(hostContract);
  const shellAllowsPrivilegedControls = shellAllowsPrivilegedRuntimeControls(hostContract);
  const allowsPrivilegedControls = shellAllowsPrivilegedControls && (privilegeRole === "root" || canElevate);
  const actionAllowed = (
    action?: { privileged?: boolean | null; required_role?: string | null } | null,
  ) => {
    if (action?.required_role === "root") return privilegeRole === "root" || canElevate;
    return !action?.privileged || allowsPrivilegedControls;
  };
  const actionRestrictionReason = (
    action?: {
      privileged?: boolean | null;
      required_role?: string | null;
      privileged_reason?: string | null;
    } | null,
  ) => {
    if (action?.required_role === "root" && !(privilegeRole === "root" || canElevate)) {
      return action.privileged_reason ?? "requires root-level privileges";
    }
    return action?.privileged && !allowsPrivilegedControls
      ? action.privileged_reason ?? "requires elevated privileges"
      : null;
  };
  const boardSnapshot = diagnostics?.snapshot.board;
  const nativeSnapshot = diagnostics?.snapshot.native;
  const nativeLastCommand = nativeSnapshot?.last_command;
  const nativeRecentCommands = nativeSnapshot?.recent_commands?.slice(-6).reverse() ?? [];
  const nativeModuleEntries = Object.entries(nativeSnapshot?.modules ?? {});
  const profile = kernelManifest?.profile ?? null;
  const featureRows = profile?.features.slice(0, 6) ?? [];
  const toolRows = profile?.tools.slice(0, 6) ?? [];
  const runtimeTargets = kernelManifest?.targets.runtime.slice(0, 4) ?? [];
  const runtimeLanguages = kernelManifest?.targets.languages.slice(0, 4) ?? [];
  const adapterContract = kernelManifest?.targets.adapter ?? null;
  const adapterTransports = adapterContract?.transport_modes.slice(0, 5) ?? [];
  const adapterControlPlane = adapterContract?.control_plane.slice(0, 5) ?? [];
  const runtimeAdapters = kernelManifest?.runtime_adapters.slice(0, 3) ?? [];
  const runtimeBridges = kernelManifest?.runtime_bridges.slice(0, 4) ?? [];
  const runtimeModules = kernelManifest?.runtime_modules.slice(0, 6) ?? [];
  const runtimeControl = kernelManifest?.runtime_control ?? null;
  const operatorConsole = kernelManifest?.operator_console ?? null;
  const operatorActionRegistry = operatorConsole?.action_registry ?? [];
  const runtimeCapabilities = kernelManifest?.capabilities ?? null;
  const executionContract = kernelManifest?.execution ?? null;
  const diagnostics = kernelManifest?.diagnostics ?? null;
  const goalState = diagnostics?.snapshot.goal_state;
  const executionLanes = kernelManifest?.execution_lanes.slice(0, 4) ?? [];
  const sessionControls = kernelManifest?.session_controls?.actions ?? [];
  const workerControls = kernelManifest?.worker_controls?.actions ?? [];
  const scheduler = kernelManifest?.scheduler ?? null;
  const schedulerQueues = scheduler?.queues.slice(0, 4) ?? [];
  const dispatchQueue = schedulerQueues.find((queue) => queue.id === "tool_dispatch") ?? null;
  const dispatchQueueTasks = dispatchQueue?.active_tasks?.slice(0, 4) ?? [];
  const workers = kernelManifest?.workers.slice(0, 4) ?? [];
  const embeddedTopology = kernelManifest?.embedded_topology ?? null;
  const runtimeTopology = kernelManifest?.runtime_topology ?? null;
  const runtimeTopologyAdapters = runtimeTopology?.adapters?.slice(0, 4) ?? [];
  const runtimeTopologyModules = runtimeTopology?.modules?.slice(0, 6) ?? [];
  const runtimeTopologyLanes = runtimeTopology?.execution_lanes?.slice(0, 4) ?? [];
  const embeddedPorts = boardSnapshot?.available_ports?.slice(0, 6) ?? [];
  const eventLog = kernelManifest?.event_log.slice(0, 8) ?? [];
  const nativeAction = (id: string) => nativeLastCommand?.actions?.find((action) => action.id === id) ?? null;
  const selectedModuleAction = (id: string) => selectedModule?.actions?.find((action) => action.id === id) ?? null;
  const dispatchQueueAction = (id: string) => dispatchQueue?.actions?.find((action) => action.id === id) ?? null;
  const selectedBridgeAction = (id: string) => selectedBridge?.actions?.find((action) => action.id === id) ?? null;
  const faultAction = (id: string) => runtimeControl?.fault_posture.actions?.find((action) => action.id === id) ?? null;
  const runtimeTopologyAction = (id: string) => runtimeTopology?.actions?.find((action) => action.id === id) ?? null;
  const embeddedTopologyAction = (id: string) => embeddedTopology?.actions?.find((action) => action.id === id) ?? null;
  const findModuleAction = (moduleName: string, actionId: string) =>
    runtimeModules.find((module) => module.name === moduleName)?.actions?.find((action) => action.id === actionId)
    ?? runtimeTopologyModules.find((module) => module.name === moduleName)?.actions?.find((action) => action.id === actionId)
    ?? null;
  const primaryEventAction = (event?: { actions?: Array<{ pane?: string | null; command?: string | null }> | null } | null) =>
    event?.actions?.find((action) => !!action.command) ?? null;
  const executionTimeline = eventLog.slice(0, 6).map((event, index) => ({
    id: String(event.id ?? index + 1),
    type: String(event.type ?? "event"),
    state: String(event.state ?? "unknown"),
    message: String(event.message ?? "no message"),
    route: primaryEventAction(event),
  }));
  const firstEventRoute = (pane: string) => eventLog
    .map((event) => primaryEventAction(event))
    .find((action) => action?.pane === pane) ?? null;
  const handleTimelineRoute = async (route?: {
    pane?: string | null;
    command?: string | null;
  } | null) => {
    if (!route?.command) return;
    onSelectPane(route.pane ?? "workspace");
    if (!onRunOperatorCommand) return;
    try {
      const result = await onRunOperatorCommand(route.command);
      appendOperatorOutput(`$ ${route.command}`);
      appendOperatorResult(result);
    } catch (error) {
      appendOperatorOutput(error instanceof Error ? error.message : "timeline routing failed");
    }
  };
  const diagPhase = diagnostics?.snapshot.phase ?? null;
  const diagIteration = diagnostics?.snapshot.iteration ?? null;
  const diagPendingToolCalls = diagnostics?.snapshot.pending_tool_calls ?? 0;
  const diagSubagentWorkers = diagnostics?.snapshot.subagent_workers ?? 0;
  const selectedAdapter = useMemo(
    () =>
      runtimeAdapters.find((adapter) => adapter.name === selectedAdapterName)
      ?? runtimeAdapters[0]
      ?? null,
    [runtimeAdapters, selectedAdapterName],
  );
  const selectedBridge = useMemo(
    () =>
      runtimeBridges.find((bridge) => bridge.adapter === selectedAdapterName)
      ?? runtimeBridges[0]
      ?? null,
    [runtimeBridges, selectedAdapterName],
  );
  const selectedModule = useMemo(
    () =>
      runtimeModules.find((module) => module.name === selectedModuleName)
      ?? runtimeModules[0]
      ?? null,
    [runtimeModules, selectedModuleName],
  );
  const actionRegistryById = useMemo(
    () => Object.fromEntries(operatorActionRegistry.map((action) => [action.id, action])),
    [operatorActionRegistry],
  );
  const resolveActionBinding = (action: string): KernelOperatorActionBinding => {
    const binding = operatorActions?.[action];
    const registry = actionRegistryById[action];
    const onTrigger = binding?.onTrigger;
    return {
      id: binding?.id ?? action,
      label: binding?.label ?? registry?.label ?? action.replaceAll("_", " "),
      kind: binding?.kind ?? registry?.kind,
      availability: binding?.availability ?? registry?.availability,
      targetPane: binding?.targetPane ?? registry?.target_pane ?? null,
      enabled: binding?.enabled ?? typeof onTrigger === "function",
      onTrigger,
    };
  };
  const [operatorCommand, setOperatorCommand] = useState("");
  const [operatorOutput, setOperatorOutput] = useState<Array<{
    line: string;
    details?: Record<string, string | number | boolean | null>;
  }>>([
    {
      line: "mira-kernel shell ready. try `runtime health`, `native inspect memory`, `native focus memory`, `native replay runtime pause operator-ping`, or `board mode`.",
    },
  ]);
  const [operatorPending, setOperatorPending] = useState(false);
  const [operatorActiveCommand, setOperatorActiveCommand] = useState<string | null>(null);
  const appendOperatorOutput = (
    line: string,
    details?: Record<string, string | number | boolean | null>,
  ) => {
    setOperatorOutput((current) => [...current.slice(-5), { line, details }]);
  };
  const appendOperatorResult = (result?: {
    output?: string;
    targetPane?: string | null;
    details?: Record<string, string | number | boolean | null>;
    action_result?: KernelOperatorActionResult;
  }) => {
    const actionResult = result?.action_result;
    const resolvedPane = actionResult?.target_pane ?? result?.targetPane ?? null;
    if (resolvedPane) onSelectPane(resolvedPane);
    const resolvedDetails = actionResult?.details ?? result?.details ?? undefined;
    appendOperatorOutput(
      actionResult?.output ?? result?.output ?? "ok",
      actionResult
        ? {
            ...resolvedDetails,
            status: actionResult.status ?? resolvedDetails?.status ?? "ok",
            code: actionResult.code ?? resolvedDetails?.code ?? 0,
            subject: actionResult.subject ?? resolvedDetails?.subject ?? null,
            action: actionResult.action ?? resolvedDetails?.action ?? null,
          }
        : resolvedDetails,
    );
  };
  const runOperatorCommand = async () => {
    const raw = operatorCommand.trim();
    if (!raw || operatorPending) return;
    if (raw === "clear") {
      setOperatorOutput([
        {
          line: "mira-kernel shell cleared.",
        },
      ]);
      setOperatorCommand("");
      return;
    }
    setOperatorPending(true);
    setOperatorActiveCommand(raw);
    appendOperatorOutput(`$ ${raw}`);
    try {
      if (!onRunOperatorCommand) throw new Error("operator command transport unavailable");
      const result = await onRunOperatorCommand(raw);
      appendOperatorResult(result);
    } catch (error) {
      appendOperatorOutput(error instanceof Error ? error.message : "operator command failed");
    } finally {
      setOperatorPending(false);
      setOperatorActiveCommand(null);
    }
    setOperatorCommand("");
  };
  const runQuickCommand = (command: string) => {
    if (operatorPending) return;
    setOperatorCommand(command);
    void Promise.resolve().then(async () => {
      setOperatorPending(true);
      setOperatorActiveCommand(command);
      appendOperatorOutput(`$ ${command}`);
      try {
        if (!onRunOperatorCommand) throw new Error("operator command transport unavailable");
        const result = await onRunOperatorCommand(command);
        appendOperatorResult(result);
      } catch (error) {
        appendOperatorOutput(error instanceof Error ? error.message : "operator command failed");
      } finally {
        setOperatorPending(false);
        setOperatorActiveCommand(null);
      }
      setOperatorCommand("");
    });
  };
  const runTopologyCommand = (pane: string, command: string) => {
    onSelectPane(pane);
    runQuickCommand(command);
  };
  const runContractAction = (action?: {
    pane?: string | null;
    command?: string | null;
  } | null, fallbackPane = "workspace") => {
    if (!action?.command) return;
    runTopologyCommand(action.pane ?? fallbackPane, action.command);
  };
  const quickCommandGroups = [
    {
      label: "shell",
      tone: "border-zinc-700 bg-zinc-950 text-zinc-100",
      commands: ["help", "clear"],
    },
    {
      label: "runtime",
      tone: "border-cyan-700 bg-cyan-950 text-cyan-100",
      commands: ["runtime health", "runtime gate", "runtime orchestration", "runtime topology", "runtime queues", "runtime adapters", "runtime bridges"],
    },
    {
      label: "kernel",
      tone: "border-indigo-700 bg-indigo-950 text-indigo-100",
      commands: ["kernel profile", "kernel manifest", "topology embedded"],
    },
    {
      label: "execution",
      tone: "border-sky-700 bg-sky-950 text-sky-100",
      commands: ["scheduler status", "lane show", "worker show", "session status", "session goal", "session continuation"],
    },
    {
      label: "events",
      tone: "border-violet-700 bg-violet-950 text-violet-100",
      commands: ["event show", "event tail", "event tail 8"],
    },
    {
      label: "workspace",
      tone: "border-stone-700 bg-stone-950 text-stone-100",
      commands: ["workspace status", "workspace scope", "workspace modules", "workspace focus-module memory", "repo status", "repo root", "repo tools", "repo prepare-tool shell"],
    },
    {
      label: "tools",
      tone: "border-blue-700 bg-blue-950 text-blue-100",
      commands: ["tool status", "tool inspect shell", "tool inspect filesystem", "tool inspect search", "tool dispatch shell", "tool queue", "tool prioritize", "tool delegate-goal", "tool delegate-subagent", "tool complete", "tool fail", "tool drain", "tool clear-queue"],
    },
    {
      label: "bridge",
      tone: "border-emerald-700 bg-emerald-950 text-emerald-100",
      commands: ["bridge status", "bridge fault", "bridge list"],
    },
    {
      label: "adapter",
      tone: "border-slate-700 bg-slate-900 text-slate-200",
      commands: ["adapter status", "adapter list", "adapter switch rust-ffi"],
    },
    {
      label: "module",
      tone: "border-lime-700 bg-lime-950 text-lime-100",
      commands: ["module list", "module show", "module actions", "module focus memory"],
    },
    {
      label: "board",
      tone: "border-amber-700 bg-amber-950 text-amber-100",
      commands: ["board status", "board mode", "board target", "board transport", "board ports"],
    },
    {
      label: "native",
      tone: "border-fuchsia-700 bg-fuchsia-950 text-fuchsia-100",
      commands: ["native status", "native last-command", "native replay-last", "native inspect memory", "native focus memory", "native replay runtime pause operator-ping", "native modules"],
    },
    {
      label: "fault",
      tone: "border-rose-700 bg-rose-950 text-rose-100",
      commands: ["fault show", "fault clear", "fault record", "bridge fault"],
    },
    {
      label: "maintenance",
      tone: "border-fuchsia-700 bg-fuchsia-950 text-fuchsia-100",
      commands: ["maintenance status", "enter-maintenance", "exit-maintenance", "goal reset"],
    },
  ];
  const nativeReplayCommands = useMemo(() => {
    const commands = ["native status", "native last-command", "native replay-last", "native inspect memory", "native focus memory", "native modules"];
    const openLastTargetCommand = nativeAction("open_last_target")?.command;
    if (openLastTargetCommand) {
      commands.push(openLastTargetCommand);
    }
    if (selectedModuleAction("focus_native")?.command) {
      commands.push(selectedModuleAction("focus_native")!.command);
    }
    if (selectedModuleAction("inspect_native")?.command) {
      commands.push(selectedModuleAction("inspect_native")!.command);
    }
    if (selectedModuleAction("fill_native_replay")?.command) {
      commands.push(selectedModuleAction("fill_native_replay")!.command);
    }
    return commands;
  }, [nativeAction, selectedModule?.actions]);
  const paneClass = (pane: string) =>
    selectedPane === pane ? "space-y-2" : "hidden";
  const lastNativeStatus = nativeLastCommand?.status ?? "idle";
  const lastNativeCode = nativeLastCommand?.code ?? 0;
  const lastNativeCommand = nativeLastCommand?.command ?? nativeLastCommand?.action ?? "none";
  const lastNativeUpdated = nativeLastCommand?.updated_at_ms ?? null;
  const nativeFaultModules = nativeModuleEntries.filter(([, state]) => state?.status === "fault");
  const faultedBridges = runtimeBridges.filter((bridge) => bridge.health === "fault");
  const faultEventCount = executionTimeline.filter((event) => event.type.includes("fault") || event.type.includes("maintenance")).length;
  const runtimeEventCount = executionTimeline.filter((event) => event.type.includes("turn") || event.type.includes("execution") || event.type.includes("session")).length;
  const bridgeEventCount = executionTimeline.filter((event) => event.type.includes("bridge") || event.type.includes("adapter") || event.type.includes("board")).length;

  return (
    <aside className="hidden w-[320px] shrink-0 border-l border-border/70 bg-[linear-gradient(180deg,rgba(248,250,252,0.98)_0%,rgba(241,245,249,0.96)_100%)] xl:flex xl:flex-col">
      <div className="border-b border-border/70 px-4 py-3">
        <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          {appIdentity} Kernel Console
        </div>
        <div className="mt-1 text-sm font-semibold text-foreground">
          Inspect runtime, modules, workspace, and shell posture
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <ConsoleBadge label="profile" value={profile?.name ?? "unknown"} tone="slate" />
          <ConsoleBadge label="shell" value={shellMode} tone="slate" />
          <ConsoleBadge label="status" value={connectionStatus} tone={connectionStatus === "connected" ? "emerald" : "amber"} />
          <ConsoleBadge label="runs" value={`${runningExecutionCount}`} tone="slate" />
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto px-4 py-4 text-sm">
        <section className="space-y-2">
          <div className="text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Pane routing
          </div>
          <div className="flex flex-wrap gap-2">
            {(operatorConsole?.panes ?? []).map((pane) => (
              <button
                key={pane}
                type="button"
                onClick={() => onSelectPane(pane)}
                className={cn(
                  "rounded-md border px-2.5 py-1 text-[11px] uppercase tracking-[0.12em] transition-colors",
                  selectedPane === pane
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-300/80 bg-white text-slate-700 hover:bg-slate-50",
                )}
              >
                {pane}
              </button>
            ))}
          </div>
        </section>

        <section className={paneClass("control_plane")}>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Control plane
          </div>
          <div className="grid gap-3 rounded-2xl border border-slate-900 bg-[linear-gradient(135deg,#020617_0%,#0f172a_55%,#111827_100%)] p-4 text-slate-100 shadow-[0_24px_80px_rgba(15,23,42,0.28)]">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="space-y-2">
                <div className="text-[10px] uppercase tracking-[0.22em] text-cyan-200/80">
                  Mira kernel shell
                </div>
                <div className="text-2xl font-semibold tracking-[-0.03em] text-white">
                  {kernelManifest?.identity?.app_name ?? "Mira"} operator console
                </div>
                <div className="max-w-2xl text-sm text-slate-300">
                  General execution layer with runtime supervision, native bridge control, module focus,
                  board operations, and fault posture in one shell.
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <ConsoleBadge label="shell" value={shellMode} tone="slate" />
                <ConsoleBadge label="gate" value={runtimeControl?.execution_gate?.state ?? "open"} tone={runtimeControl?.execution_gate?.state === "open" ? "emerald" : "amber"} />
                <ConsoleBadge label="board" value={boardSnapshot?.attached ? "attached" : "detached"} tone={boardSnapshot?.attached ? "emerald" : "amber"} />
                <ConsoleBadge label="native" value={nativeSnapshot?.health ?? "unknown"} tone={nativeSnapshot?.health === "ready" ? "emerald" : "amber"} />
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-xl border border-white/10 bg-white/5 p-3">
                <div className="text-[10px] uppercase tracking-[0.16em] text-slate-400">Privilege</div>
                <div className="mt-2 flex items-center gap-2">
                  <span className={cn(
                    "rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.14em]",
                    privilegeRole === "root"
                      ? "border-emerald-400/40 bg-emerald-500/15 text-emerald-100"
                      : "border-amber-400/40 bg-amber-500/15 text-amber-100",
                  )}>
                    {privilegeRole}
                  </span>
                  <span className="text-xs text-slate-300">
                    {shellAllowsPrivilegedControls ? (canElevate && privilegeRole !== "root" ? "elevation-capable" : "operator-ready") : "restricted shell"}
                  </span>
                </div>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/5 p-3">
                <div className="text-[10px] uppercase tracking-[0.16em] text-slate-400">Runtime</div>
                <div className="mt-2 text-lg font-semibold text-white">{runtimeModel ?? "unresolved"}</div>
                <div className="text-xs text-slate-300">
                  {runtimeControl?.execution_gate?.reason ?? "operator-ready"}
                </div>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/5 p-3">
                <div className="text-[10px] uppercase tracking-[0.16em] text-slate-400">Module focus</div>
                <div className="mt-2 text-lg font-semibold text-white">
                  {selectedModule?.name ?? "unfocused"}
                </div>
                <div className="text-xs text-slate-300">
                  native queue {(nativeSnapshot?.queue_depth ?? nativeSnapshot?.command_depth ?? 0)} / modules {nativeSnapshot?.module_count ?? runtimeModules.length}
                </div>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/5 p-3">
                <div className="text-[10px] uppercase tracking-[0.16em] text-slate-400">Board target</div>
                <div className="mt-2 text-lg font-semibold text-white">
                  {boardSnapshot?.target ?? embeddedTargetHint ?? "host"}
                </div>
                <div className="text-xs text-slate-300">
                  {boardSnapshot?.transport ?? boardSnapshot?.preferred_transport ?? "unset"} · {boardSnapshot?.port ?? "auto"}
                </div>
              </div>
            </div>
          </div>
          <div className="grid gap-2 rounded-xl border border-border/70 bg-background/80 p-3">
            <Row label="Profile" value={profile?.name ?? "unknown"} />
            <Row label="Shell" value={shellDescriptor?.display_name ?? "Mira"} />
            <Row label="Mode" value={shellMode} />
            <Row label="Status" value={connectionStatus} />
            <Row label="Model" value={runtimeModel ?? "unresolved"} />
            <Row label="Running" value={`${runningExecutionCount}`} />
            <Row label="Gate" value={runtimeControl?.execution_gate?.state ?? "open"} />
            <Row
              label="Maintenance"
              value={runtimeControl?.maintenance_mode?.enabled ? "enabled" : "off"}
            />
            <Row
              label="Gate reason"
              value={runtimeControl?.execution_gate?.reason ?? "operator-ready"}
            />
            <Row
              label="Supervisor"
              value={diagnostics?.supervisor ?? runtimeControl?.fault_posture.supervisor ?? "unknown"}
            />
            <div className="mt-3 flex flex-wrap gap-2">
              <AdapterActionButton binding={resolveActionBinding("enter_maintenance")} />
              <AdapterActionButton binding={resolveActionBinding("exit_maintenance")} />
            </div>
          </div>
          <div className="grid gap-2 rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Kernel identity
            </div>
            <Row label="App" value={kernelManifest?.identity?.app_name ?? "Mira"} />
            <Row label="CLI" value={kernelManifest?.identity?.cli_name ?? "mira"} />
            <Row label="Compat alias" value={kernelManifest?.identity?.legacy_cli_name ?? "mira"} />
            <Row label="Profile" value={profile?.name ?? "unknown"} />
            <Row label="Privilege" value={privilegeRole} />
            <Row label="Privileged shell" value={shellAllowsPrivilegedControls ? "enabled" : "restricted"} />
            <Row label="Elevation" value={canElevate ? "allowed" : "fixed"} />
            <Row label="GUI" value={runtimeCapabilities?.gui ? "enabled" : "off"} />
            <Row label="API" value={runtimeCapabilities?.api ? "enabled" : "off"} />
            <Row label="Threads" value={runtimeCapabilities?.threads ? "enabled" : "off"} />
            <Row label="Approvals" value={runtimeCapabilities?.approvals ? "enabled" : "off"} />
            <Row
              label="Contracts"
              value={`m${kernelManifest?.contracts?.manifest_version ?? 0}/e${kernelManifest?.contracts?.event_version ?? 0}/s${kernelManifest?.contracts?.snapshot_version ?? 0}`}
            />
            <div className="mt-2 flex flex-wrap gap-2">
              {runtimeTargets.length ? runtimeTargets.map((target) => (
                <span
                  key={target}
                  className="rounded-full border border-slate-300/80 bg-slate-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700"
                >
                  {target}
                </span>
              )) : null}
              {runtimeLanguages.length ? runtimeLanguages.map((language) => (
                <span
                  key={language}
                  className="rounded-full border border-cyan-300/80 bg-cyan-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-cyan-700"
                >
                  {language}
                </span>
              )) : selectedBridgeAction("restart_bridge") ? (
                <span className="text-xs text-muted-foreground">
                  {actionRestrictionReason(selectedBridgeAction("restart_bridge"))}
                </span>
              ) : faultAction("clear_faults") ? (
                <span className="text-xs text-muted-foreground">
                  {actionRestrictionReason(faultAction("clear_faults"))}
                </span>
              ) : null}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => runTopologyCommand("control_plane", "kernel profile")}
                disabled={operatorPending}
                className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
              >
                profile
              </button>
              <button
                type="button"
                onClick={() => runTopologyCommand("control_plane", "kernel manifest")}
                disabled={operatorPending}
                className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
              >
                manifest
              </button>
            </div>
          </div>
          <div className="grid gap-2 rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Operator shell
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-lg border border-slate-800 bg-slate-950/95 px-3 py-2">
                <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500">Command path</div>
                <div className="mt-2 text-sm font-semibold text-slate-50">
                  {selectedPane}
                </div>
                <div className="text-xs text-slate-400">
                  {operatorPending ? "foreground execution active" : "operator shell ready"}
                </div>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/95 px-3 py-2">
                <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500">Privilege posture</div>
                <div className="mt-2 text-sm font-semibold text-slate-50">
                  {privilegeRole}
                </div>
                <div className="text-xs text-slate-400">
                  {shellAllowsPrivilegedControls ? "runtime control contract enabled" : "restricted shell contract"}
                </div>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/95 px-3 py-2">
                <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500">Native replay</div>
                <div className="mt-2 text-sm font-semibold text-slate-50">
                  {nativeLastCommand?.target ?? "none"}:{nativeLastCommand?.action ?? "idle"}
                </div>
                <div className="text-xs text-slate-400">
                  queue {(nativeSnapshot?.queue_depth ?? nativeSnapshot?.command_depth ?? 0)} · health {nativeSnapshot?.health ?? "unknown"}
                </div>
              </div>
            </div>
            <div className="rounded-md border border-slate-300/80 bg-slate-950 px-3 py-2 font-mono text-[11px] text-slate-100">
              <div className="mb-2 flex items-center justify-between gap-3 text-slate-400">
                <span>mira-kernel@{shellMode}:{selectedPane}$</span>
                <span className={cn(
                  "rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.12em]",
                  operatorPending
                    ? "border-cyan-700 bg-cyan-950 text-cyan-100"
                    : "border-slate-700 bg-slate-900 text-slate-300",
                )}>
                  {operatorPending ? "running" : "idle"}
                </span>
              </div>
              {operatorActiveCommand ? (
                <div className="mb-2 truncate text-[10px] text-cyan-200">
                  active: {operatorActiveCommand}
                </div>
              ) : null}
              <div className="flex gap-2">
                <input
                  value={operatorCommand}
                  onChange={(event) => setOperatorCommand(event.target.value)}
                  disabled={operatorPending}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      runOperatorCommand();
                    }
                  }}
                  placeholder="runtime health | native replay runtime pause operator-ping | board attach /dev/ttyUSB0 serial"
                  className="flex-1 bg-transparent text-slate-100 outline-none placeholder:text-slate-500"
                />
                <button
                  type="button"
                  onClick={runOperatorCommand}
                  disabled={operatorPending}
                  className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-slate-100 transition-colors hover:bg-slate-800"
                >
                  {operatorPending ? "Running" : "Run"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (operatorPending) return;
                    setOperatorOutput([
                      {
                        line: "mira-kernel shell cleared.",
                      },
                    ]);
                    setOperatorCommand("");
                  }}
                  disabled={operatorPending}
                  className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-slate-100 transition-colors hover:bg-slate-800"
                >
                  Clear
                </button>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
                <span>try native injection:</span>
                <button
                  type="button"
                  onClick={() => setOperatorCommand("native replay runtime pause operator-ping")}
                  disabled={operatorPending}
                  className="rounded-full border border-fuchsia-700/60 bg-fuchsia-950 px-2 py-0.5 uppercase tracking-[0.12em] text-fuchsia-100 transition-colors hover:bg-fuchsia-900"
                >
                  native replay runtime pause operator-ping
                </button>
                {selectedModule?.name ? (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        const command = selectedModuleAction("inspect_native")?.command;
                        if (!command) return;
                        setOperatorCommand(command);
                      }}
                      disabled={operatorPending || !selectedModuleAction("inspect_native")?.command}
                      className="rounded-full border border-fuchsia-700/60 bg-fuchsia-950 px-2 py-0.5 uppercase tracking-[0.12em] text-fuchsia-100 transition-colors hover:bg-fuchsia-900"
                    >
                      native inspect {selectedModule.name}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        const command = selectedModuleAction("fill_native_replay")?.command;
                        if (!command) return;
                        setOperatorCommand(command);
                      }}
                      disabled={operatorPending || !selectedModuleAction("fill_native_replay")?.command}
                      className="rounded-full border border-fuchsia-700/60 bg-fuchsia-950 px-2 py-0.5 uppercase tracking-[0.12em] text-fuchsia-100 transition-colors hover:bg-fuchsia-900"
                    >
                      native replay {selectedModule.name} inspect status
                    </button>
                  </>
                ) : dispatchQueueAction("prioritize_dispatch") ? (
                  <span className="text-xs text-muted-foreground">
                    {actionRestrictionReason(dispatchQueueAction("prioritize_dispatch"))}
                  </span>
                ) : null}
              </div>
              <div className="mt-3 space-y-2">
                {quickCommandGroups.map((group) => (
                  <div key={group.label} className="space-y-1">
                    <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500">
                      {group.label}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {group.commands.map((command) => (
                        <button
                          key={command}
                          type="button"
                          onClick={() => runQuickCommand(command)}
                          disabled={operatorPending}
                          className={cn(
                            "rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] transition-colors",
                            group.tone,
                            operatorPending ? "opacity-60" : "",
                          )}
                        >
                          {command}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => runQuickCommand("runtime health")}
                  disabled={operatorPending}
                  className="rounded-full border border-cyan-700 bg-cyan-950 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-cyan-100 transition-colors hover:bg-cyan-900"
                >
                  run probe
                </button>
                <div className="space-y-1">
                  <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500">
                    native replay
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {nativeReplayCommands.map((command) => (
                      <button
                        key={command}
                        type="button"
                        onClick={() => runQuickCommand(command)}
                        disabled={operatorPending}
                        className={cn(
                          "rounded-full border border-fuchsia-700 bg-fuchsia-950 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-100 transition-colors hover:bg-fuchsia-900",
                          operatorPending ? "opacity-60" : "",
                        )}
                      >
                        {command}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
            <div className="space-y-2 rounded-md border border-slate-200/80 bg-white/80 px-2.5 py-2 font-mono text-[11px] text-slate-700">
              {operatorOutput.map((entry, index) => (
                <div
                  key={`${entry.line}-${index}`}
                  className={cn(
                    "rounded-md border px-2.5 py-2",
                    operatorPanelTone(
                      entry.details && "subject" in entry.details
                        ? String(entry.details.subject)
                        : null,
                    ),
                  )}
                >
                  <div className="truncate text-slate-800">
                    {entry.line}
                  </div>
                  {entry.details ? (
                    <>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {"subject" in entry.details ? (
                          <ConsoleBadge
                            label="subject"
                            value={String(entry.details.subject)}
                            tone="slate"
                          />
                        ) : null}
                        {"action" in entry.details ? (
                          <ConsoleBadge
                            label="action"
                            value={String(entry.details.action)}
                            tone="emerald"
                          />
                        ) : null}
                      </div>
                      <div className="mt-2 grid gap-1.5 text-[10px] text-slate-500">
                        {Object.entries(entry.details)
                          .filter(([key]) => key !== "subject" && key !== "action")
                          .map(([key, value]) => (
                            key === "items" || key === "codes" || key === "updated" ? (
                              <div
                                key={key}
                                className="rounded-sm border border-slate-200/80 bg-white/80 px-2 py-1"
                              >
                                <div className="mb-1 uppercase tracking-[0.12em]">{key}</div>
                                <div className="flex flex-wrap gap-1">
                                  {String(value)
                                    .split(",")
                                    .map((item) => item.trim())
                                    .filter(Boolean)
                                    .map((item) => (
                                      <button
                                        key={item}
                                        type="button"
                                        onClick={() => {
                                          if (
                                            entry.details?.subject === "native"
                                            && entry.details?.action === "modules"
                                            && item.includes(":")
                                          ) {
                                            const moduleName = item.split(":")[0];
                                            const action = key === "items"
                                              ? findModuleAction(moduleName, "show_module")
                                              : findModuleAction(moduleName, "focus_native");
                                            if (!action?.command) return;
                                            if (key === "items") {
                                              runQuickCommand(action.command);
                                            } else {
                                              runQuickCommand(action.command);
                                            }
                                          }
                                        }}
                                        disabled={operatorPending}
                                        className="rounded-full border border-slate-300/80 bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-700 transition-colors hover:bg-slate-100 disabled:cursor-default disabled:hover:bg-slate-50"
                                      >
                                        {item}
                                      </button>
                                    ))}
                                </div>
                              </div>
                            ) : (
                              <div
                                key={key}
                                className="flex items-center justify-between gap-3 rounded-sm border border-slate-200/80 bg-white/80 px-2 py-1"
                              >
                                <span className="uppercase tracking-[0.12em]">{key}</span>
                                <span className="truncate text-slate-700">
                                  {key === "updated_at_ms"
                                    ? formatKernelTimestamp(value)
                                    : key === "updated"
                                      ? formatKernelTimestampList(String(value))
                                      : String(value)}
                                </span>
                              </div>
                            )
                          ))}
                      </div>
                      {entry.details.subject === "native" ? (
                        <div className="mt-2 flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => runQuickCommand("native status")}
                            disabled={operatorPending}
                            className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                          >
                            refresh native
                          </button>
                          <button
                            type="button"
                            onClick={() => runQuickCommand("native replay-last")}
                            disabled={operatorPending}
                            className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                          >
                            replay last
                          </button>
                          <button
                            type="button"
                            onClick={() => runQuickCommand("native last-command")}
                            disabled={operatorPending}
                            className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                          >
                            inspect last
                          </button>
                          {"target" in entry.details && "command" in entry.details ? (
                            <button
                              type="button"
                              onClick={() => setOperatorCommand(
                                `native replay ${String(entry.details.target)} ${String(entry.details.command)}${
                                  entry.details.value ? ` ${String(entry.details.value)}` : ""
                                }`,
                              )}
                              disabled={operatorPending}
                              className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                            >
                              fill replay
                            </button>
                          ) : null}
                          {"target" in entry.details && entry.details.target ? (
                            <button
                              type="button"
                              onClick={() => runQuickCommand(`native focus ${String(entry.details.target)}`)}
                              disabled={operatorPending}
                              className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                            >
                              focus target
                            </button>
                          ) : null}
                          {"target" in entry.details && entry.details.target ? (
                            <button
                              type="button"
                              onClick={() => {
                                const action = findModuleAction(String(entry.details.target), "show_module");
                                if (!action?.command) return;
                                runQuickCommand(action.command);
                              }}
                              disabled={operatorPending || !findModuleAction(String(entry.details.target), "show_module")?.command}
                              className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                            >
                              open module
                            </button>
                          ) : null}
                          {"target" in entry.details && entry.details.target ? (
                            <button
                              type="button"
                              onClick={() => {
                                const command = findModuleAction(String(entry.details.target), "fill_native_inspect")?.command;
                                if (!command) return;
                                setOperatorCommand(command);
                              }}
                              disabled={operatorPending || !findModuleAction(String(entry.details.target), "fill_native_inspect")?.command}
                              className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                            >
                              fill inspect
                            </button>
                          ) : null}
                        </div>
                      ) : null}
                    </>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className={paneClass("runtime")}>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Active execution
          </div>
          <div className="rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="truncate font-medium text-foreground">
              {activeExecution?.title || activeExecution?.preview || "No active execution"}
            </div>
            <div className="mt-1 truncate text-xs text-muted-foreground">
              {activeExecution?.chatId ?? "Detached shell state"}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <ConsoleBadge label="streaming" value={executionContract?.supports_streaming ? "on" : "off"} tone="slate" />
              <ConsoleBadge label="background" value={executionContract?.supports_background ? "on" : "off"} tone="slate" />
              <ConsoleBadge label="engine" value={runtimeCapabilities?.can_restart_engine ? "restartable" : "fixed"} tone={runtimeCapabilities?.can_restart_engine ? "emerald" : "amber"} />
              <ConsoleBadge
                label="gate"
                value={runtimeControl?.execution_gate?.state ?? "open"}
                tone={runtimeControl?.execution_gate?.state === "open" ? "emerald" : "amber"}
              />
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <AdapterActionButton binding={resolveActionBinding("pause_runtime")} />
              <AdapterActionButton binding={resolveActionBinding("resume_runtime")} />
              <AdapterActionButton binding={resolveActionBinding("degrade_runtime")} />
              <AdapterActionButton binding={resolveActionBinding("drain_background")} />
              <AdapterActionButton binding={resolveActionBinding("prioritize_goal_lane")} />
            </div>
          </div>
        </section>

        <section className={paneClass("runtime")}>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Task kernel
          </div>
          <div className="space-y-3 rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="grid gap-2 md:grid-cols-2">
              <div className="rounded-lg border border-slate-200/80 bg-slate-50/80 p-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  Session
                </div>
                <div className="mt-2 space-y-2">
                  <Row label="Chat" value={activeExecution?.chatId ?? "detached"} />
                  <Row label="Phase" value={diagPhase ?? "idle"} />
                  <Row label="Iteration" value={`${diagIteration ?? 0}`} />
                  <Row label="Pending tools" value={`${diagPendingToolCalls}`} />
                  <Row label="Subagents" value={`${diagSubagentWorkers}`} />
                  <Row
                    label="Dispatch depth"
                    value={`${diagnostics?.snapshot.dispatch_queue_depth ?? dispatchQueue?.depth ?? 0}`}
                  />
                </div>
              </div>
              <div className="rounded-lg border border-cyan-200/80 bg-cyan-50/70 p-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-cyan-700">
                  Goal lane
                </div>
                <div className="mt-2 space-y-2">
                  <Row
                    label="Background"
                    value={scheduler?.background_drain_requested ? "draining" : "idle"}
                  />
                  <Row label="Preferred lane" value={scheduler?.preferred_lane ?? "interactive"} />
                  <Row
                    label="Gate"
                    value={runtimeControl?.execution_gate?.state ?? "open"}
                  />
                  <Row
                    label="Reason"
                    value={runtimeControl?.execution_gate?.reason ?? "operator-ready"}
                  />
                  <Row
                    label="Dispatch handoff"
                    value={diagnostics?.snapshot.dispatch_handoff_lane ?? "none"}
                  />
                  <Row
                    label="Contract owner"
                    value={diagnostics?.snapshot.dispatch_contract?.owner ?? "interactive"}
                  />
                  <Row
                    label="Contract mode"
                    value={diagnostics?.snapshot.dispatch_contract?.mode ?? "direct"}
                  />
                </div>
              </div>
            </div>
            <div className="rounded-lg border border-violet-200/80 bg-violet-50/60 p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-violet-700">
                  Goal recovery
                </div>
                <ConsoleBadge
                  label="goal"
                  value={goalState?.active ? "active" : "idle"}
                  tone={goalState?.active ? "amber" : "slate"}
                />
              </div>
              <div className="mt-2 grid gap-2 md:grid-cols-2">
                <Row label="Summary" value={goalState?.ui_summary ?? "none"} />
                <Row label="Continuation rounds" value={`${goalState?.continuation_rounds ?? 0}`} />
                <Row label="Last progress" value={goalState?.last_progress_at ?? "none"} />
                <Row label="Objective" value={goalState?.objective ?? "none"} />
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => runContractAction(sessionControls[1], "runtime")}
                  disabled={operatorPending || !sessionControls[1]?.command}
                  className="rounded-full border border-violet-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-violet-700 transition-colors hover:bg-violet-100"
                >
                  inspect goal
                </button>
                <button
                  type="button"
                  onClick={() => runContractAction(sessionControls[2], "runtime")}
                  disabled={operatorPending || !sessionControls[2]?.command}
                  className="rounded-full border border-violet-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-violet-700 transition-colors hover:bg-violet-100"
                >
                  inspect continuation
                </button>
              </div>
            </div>
            <div className="rounded-lg border border-emerald-200/80 bg-emerald-50/60 p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-700">
                  Recovery posture
                </div>
                <ConsoleBadge
                  label="resume"
                  value={
                    goalState?.active
                    || (diagnostics?.snapshot.dispatch_queue_depth ?? 0) > 0
                    || diagSubagentWorkers > 0
                      ? "warm"
                      : "idle"
                  }
                  tone={
                    goalState?.active
                    || (diagnostics?.snapshot.dispatch_queue_depth ?? 0) > 0
                    || diagSubagentWorkers > 0
                      ? "amber"
                      : "slate"
                  }
                />
              </div>
              <div className="mt-2 grid gap-2 md:grid-cols-2">
                <Row label="Session" value={activeExecution?.chatId ? "attached" : "detached"} />
                <Row label="Goal state" value={goalState?.active ? "recoverable" : "idle"} />
                <Row label="Dispatch backlog" value={`${diagnostics?.snapshot.dispatch_queue_depth ?? 0}`} />
                <Row label="Handoff lane" value={diagnostics?.snapshot.dispatch_handoff_lane ?? "none"} />
                <Row label="Subagent workers" value={`${diagSubagentWorkers}`} />
                <Row label="Pending tools" value={`${diagPendingToolCalls}`} />
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => runContractAction(sessionControls[0], "runtime")}
                  disabled={operatorPending || !sessionControls[0]?.command}
                  className="rounded-full border border-emerald-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-emerald-700 transition-colors hover:bg-emerald-100"
                >
                  inspect session
                </button>
                <button
                  type="button"
                  onClick={() => runContractAction(sessionControls[2], "runtime")}
                  disabled={operatorPending || !sessionControls[2]?.command}
                  className="rounded-full border border-emerald-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-emerald-700 transition-colors hover:bg-emerald-100"
                >
                  inspect resume path
                </button>
                <button
                  type="button"
                  onClick={() => runTopologyCommand("runtime", "tool status")}
                  disabled={operatorPending}
                  className="rounded-full border border-emerald-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-emerald-700 transition-colors hover:bg-emerald-100"
                >
                  inspect backlog
                </button>
              </div>
            </div>
            <div className="rounded-lg border border-blue-200/80 bg-blue-50/60 p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-blue-700">
                  Dispatch lifecycle
                </div>
                <ConsoleBadge
                  label="queue"
                  value={diagnostics?.snapshot.dispatch_queue_state ?? dispatchQueue?.state ?? "ready"}
                  tone={dispatchQueue?.depth ? "amber" : "slate"}
                />
              </div>
              <div className="mt-2 grid gap-2 md:grid-cols-2">
                <Row label="Depth" value={`${dispatchQueue?.depth ?? 0}`} />
                <Row label="Lane" value={dispatchQueue?.lane ?? "interactive"} />
                <Row label="Class" value={dispatchQueue?.job_class ?? "tool_contract_dispatch"} />
                <Row label="Handoff" value={diagnostics?.snapshot.dispatch_handoff_lane ?? "none"} />
                <Row label="Owner" value={dispatchQueue?.dispatch_contract?.owner ?? diagnostics?.snapshot.dispatch_contract?.owner ?? "interactive"} />
                <Row label="Mode" value={dispatchQueue?.dispatch_contract?.mode ?? diagnostics?.snapshot.dispatch_contract?.mode ?? "direct"} />
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {dispatchQueueTasks.length ? dispatchQueueTasks.map((task) => (
                  <span
                    key={task}
                    className="rounded-full border border-blue-300/80 bg-white px-2 py-0.5 text-[11px] text-blue-700"
                  >
                    {task}
                  </span>
                )) : (
                  <span className="text-xs text-muted-foreground">No queued dispatch tasks.</span>
                )}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => runContractAction(dispatchQueueAction("inspect_dispatch"), "runtime")}
                  disabled={operatorPending || !dispatchQueueAction("inspect_dispatch")?.command}
                  className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
                >
                  inspect
                </button>
                {actionAllowed(dispatchQueueAction("prioritize_dispatch")) ? (
                  <>
                    <button
                      type="button"
                      onClick={() => runContractAction(dispatchQueueAction("prioritize_dispatch"), "runtime")}
                      disabled={operatorPending || !dispatchQueueAction("prioritize_dispatch")?.command}
                      className="rounded-full border border-amber-300/80 bg-amber-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-amber-700 transition-colors hover:bg-amber-100"
                    >
                      prioritize
                    </button>
                    <button
                      type="button"
                      onClick={() => runContractAction(dispatchQueueAction("delegate_goal"), "runtime")}
                      disabled={operatorPending || !dispatchQueueAction("delegate_goal")?.command}
                      className="rounded-full border border-cyan-300/80 bg-cyan-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-cyan-700 transition-colors hover:bg-cyan-100"
                    >
                      goal lane
                    </button>
                    <button
                      type="button"
                      onClick={() => runContractAction(dispatchQueueAction("delegate_subagent"), "runtime")}
                      disabled={operatorPending || !dispatchQueueAction("delegate_subagent")?.command}
                      className="rounded-full border border-violet-300/80 bg-violet-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-violet-700 transition-colors hover:bg-violet-100"
                    >
                      subagent
                    </button>
                    <button
                      type="button"
                      onClick={() => runContractAction(dispatchQueueAction("complete_dispatch"), "runtime")}
                      disabled={operatorPending || !dispatchQueueAction("complete_dispatch")?.command}
                      className="rounded-full border border-emerald-300/80 bg-emerald-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-emerald-700 transition-colors hover:bg-emerald-100"
                    >
                      complete
                    </button>
                    <button
                      type="button"
                      onClick={() => runContractAction(dispatchQueueAction("fail_dispatch"), "faults")}
                      disabled={operatorPending || !dispatchQueueAction("fail_dispatch")?.command}
                      className="rounded-full border border-rose-300/80 bg-rose-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-rose-700 transition-colors hover:bg-rose-100"
                    >
                      fail
                    </button>
                    <button
                      type="button"
                      onClick={() => runContractAction(dispatchQueueAction("drain_dispatch"), "runtime")}
                      disabled={operatorPending || !dispatchQueueAction("drain_dispatch")?.command}
                      className="rounded-full border border-slate-300/80 bg-slate-100 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-200"
                    >
                      drain
                    </button>
                    <button
                      type="button"
                      onClick={() => runContractAction(dispatchQueueAction("clear_dispatch"), "runtime")}
                      disabled={operatorPending || !dispatchQueueAction("clear_dispatch")?.command}
                      className="rounded-full border border-slate-300/80 bg-slate-100 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-200"
                    >
                      clear
                    </button>
                  </>
                ) : null}
              </div>
            </div>
            <div className="rounded-lg border border-slate-200/80 bg-slate-50/80 p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  Execution timeline
                </div>
                <div className="flex flex-wrap gap-2">
                  <ConsoleBadge label="phase" value={diagPhase ?? "idle"} tone="slate" />
                  <ConsoleBadge label="iter" value={`${diagIteration ?? 0}`} tone="slate" />
                </div>
              </div>
              <div className="mt-3 space-y-0">
                {executionTimeline.length ? executionTimeline.map((event, index) => (
                  <div key={`${event.id}-${event.type}`} className="grid grid-cols-[28px_1fr] gap-3">
                    <div className="flex flex-col items-center">
                      <div className="flex h-7 w-7 items-center justify-center rounded-full border border-slate-300/80 bg-white text-[10px] font-semibold text-slate-700">
                        {event.id}
                      </div>
                      {index < executionTimeline.length - 1 ? (
                        <div className="h-6 w-px bg-slate-300/80" />
                      ) : null}
                    </div>
                    <div className="pb-3">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-slate-900">{event.type}</span>
                        <span className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-600">
                          {event.state}
                        </span>
                        <button
                          type="button"
                          onClick={() => void handleTimelineRoute(event.route)}
                          className="rounded-full border border-slate-300/80 bg-slate-100 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-200"
                        >
                          route
                        </button>
                      </div>
                      <div className="mt-1 text-[11px] text-slate-600">
                        {event.message}
                      </div>
                    </div>
                  </div>
                )) : (
                  <div className="text-xs text-muted-foreground">No execution timeline available.</div>
                )}
              </div>
            </div>
            <div className="grid gap-3 xl:grid-cols-[1.2fr_0.8fr]">
              <div className="rounded-lg border border-violet-200/80 bg-violet-50/60 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-violet-700">
                    Kernel event stream
                  </div>
                  <ConsoleBadge label="events" value={`${eventLog.length}`} tone="slate" />
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void handleTimelineRoute(firstEventRoute("faults"))}
                    disabled={operatorPending || !firstEventRoute("faults")?.command}
                    className="rounded-full border border-rose-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-rose-700 transition-colors hover:bg-rose-100"
                  >
                    fault lane {faultEventCount}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleTimelineRoute(firstEventRoute("runtime"))}
                    disabled={operatorPending || !firstEventRoute("runtime")?.command}
                    className="rounded-full border border-cyan-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-cyan-700 transition-colors hover:bg-cyan-100"
                  >
                    runtime lane {runtimeEventCount}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleTimelineRoute(firstEventRoute("adapters"))}
                    disabled={operatorPending || !firstEventRoute("adapters")?.command}
                    className="rounded-full border border-amber-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-amber-700 transition-colors hover:bg-amber-100"
                  >
                    bridge lane {bridgeEventCount}
                  </button>
                </div>
                <div className="mt-3 space-y-2">
                  {eventLog.length ? eventLog.slice(0, 5).map((event, index) => (
                    <button
                      key={`${event.id ?? "event"}-${index}`}
                      type="button"
                      onClick={() => void handleTimelineRoute(primaryEventAction(event))}
                      disabled={operatorPending || !primaryEventAction(event)?.command}
                      className="w-full rounded-md border border-violet-200/80 bg-white/80 px-2.5 py-2 text-left transition-colors hover:bg-violet-100/60"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="truncate font-medium text-slate-900">
                          {event.type ?? "event"}
                        </span>
                        <span className="rounded-full border border-violet-200/80 bg-violet-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-violet-700">
                          {event.state ?? "unknown"}
                        </span>
                      </div>
                      <div className="mt-1 text-[11px] text-slate-600">
                        {event.message ?? "no message"}
                      </div>
                    </button>
                  )) : (
                    <div className="text-xs text-muted-foreground">No kernel events captured.</div>
                  )}
                </div>
              </div>
              <div className="rounded-lg border border-rose-200/80 bg-rose-50/60 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-rose-700">
                    Error signal
                  </div>
                  <ConsoleBadge label="recent" value={`${recentErrors.length}`} tone="amber" />
                </div>
                <div className="mt-3 space-y-2">
                  {recentErrors.length ? recentErrors.slice(0, 3).map((entry, index) => (
                    <div
                      key={`${entry.id}-${index}`}
                      className="rounded-md border border-rose-200/80 bg-white/85 px-2.5 py-2"
                    >
                      <div className="truncate font-medium text-slate-900">
                        {entry.kind}
                      </div>
                      <div className="mt-1 text-[11px] text-slate-600">
                        {entry.message}
                      </div>
                    </div>
                  )) : (
                    <div className="text-xs text-muted-foreground">No recent shell errors.</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className={paneClass("modules")}>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Modules
          </div>
          <div className="space-y-3 rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="flex flex-wrap gap-2">
              {runtimeModules.length ? runtimeModules.map((module) => (
                <div key={module.name} className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => onSelectModule(module.name)}
                    className={cn(
                      "rounded-full border px-2.5 py-1 text-[11px] transition-colors",
                      selectedModule?.name === module.name
                        ? "border-slate-900 bg-slate-900 text-white"
                        : "border-slate-300/80 bg-slate-100 text-slate-700 hover:bg-slate-50",
                    )}
                  >
                    <span>{module.display_name}</span>
                    {"native_status" in module ? (
                      <span
                        className={cn(
                          "ml-2 rounded-full px-1.5 py-0.5 text-[9px] uppercase tracking-[0.12em]",
                          module.native_status === "fault"
                            ? "bg-rose-100 text-rose-700"
                            : module.native_status === "busy"
                              ? "bg-amber-100 text-amber-700"
                              : "bg-fuchsia-100 text-fuchsia-700",
                        )}
                      >
                        {String(module.native_status)}
                      </span>
                    ) : null}
                  </button>
                  {"native_status" in module ? (
                    <button
                      type="button"
                      onClick={() => runQuickCommand(`native inspect ${module.name}`)}
                      disabled={operatorPending}
                      className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                    >
                      inspect
                    </button>
                  ) : null}
                </div>
              )) : featureRows.map((feature) => (
                <span
                  key={feature}
                  className="rounded-full border border-slate-300/80 bg-slate-100 px-2.5 py-1 text-xs text-slate-700"
                >
                  {feature}
                </span>
              ))}
            </div>
            {selectedModule ? (
              <div className="rounded-lg border border-slate-300/70 bg-slate-50/80 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium text-foreground">{selectedModule.display_name}</div>
                  <span className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[11px] text-slate-600">
                    {selectedModule.status}
                  </span>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {selectedModule.category} · {selectedModule.summary}
                </div>
                <div className="mt-3 grid gap-2 md:grid-cols-4">
                  <div className="rounded-lg border border-lime-200/70 bg-lime-50/80 p-3">
                    <div className="text-[10px] uppercase tracking-[0.14em] text-lime-700">Focus status</div>
                    <div className="mt-2 text-sm font-semibold text-lime-950">
                      {runtimeControl?.module_focus === selectedModule.name ? "active" : "standby"}
                    </div>
                  </div>
                  <div className="rounded-lg border border-slate-200/70 bg-white/80 p-3">
                    <div className="text-[10px] uppercase tracking-[0.14em] text-slate-600">Operator actions</div>
                    <div className="mt-2 text-lg font-semibold text-slate-950">
                      {selectedModule.operator_actions.length}
                    </div>
                  </div>
                  <div className="rounded-lg border border-fuchsia-200/70 bg-fuchsia-50/80 p-3">
                    <div className="text-[10px] uppercase tracking-[0.14em] text-fuchsia-700">Native posture</div>
                    <div className="mt-2 text-sm font-semibold text-fuchsia-950">
                      {"native_status" in selectedModule ? String(selectedModule.native_status ?? "unknown") : "not-wired"}
                    </div>
                  </div>
                  <div className="rounded-lg border border-amber-200/70 bg-amber-50/80 p-3">
                    <div className="text-[10px] uppercase tracking-[0.14em] text-amber-700">Last code</div>
                    <div className="mt-2 text-sm font-semibold text-amber-950">
                      {"native_last_code" in selectedModule ? String(selectedModule.native_last_code ?? 0) : "n/a"}
                    </div>
                  </div>
                </div>
                {"native_status" in selectedModule ? (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <ConsoleBadge
                      label="native"
                      value={String(selectedModule.native_status ?? "unknown")}
                      tone="fuchsia"
                    />
                    {"native_last_code" in selectedModule ? (
                      <ConsoleBadge
                        label="code"
                        value={String(selectedModule.native_last_code ?? 0)}
                        tone="amber"
                      />
                    ) : null}
                    {"native_updated_at_ms" in selectedModule && selectedModule.native_updated_at_ms ? (
                      <ConsoleBadge
                        label="updated"
                        value={formatKernelTimestamp(selectedModule.native_updated_at_ms)}
                        tone="slate"
                      />
                    ) : null}
                  </div>
                ) : null}
                {runtimeControl?.module_focus ? (
                  <div className="mt-3 rounded-md border border-slate-200/80 bg-white/80 px-2.5 py-2 text-[11px] uppercase tracking-[0.12em] text-slate-500">
                    Focus pointer: <span className="font-semibold text-slate-900">{runtimeControl.module_focus}</span>
                  </div>
                ) : null}
                <div className="mt-3 flex flex-wrap gap-2">
                  {selectedModule.operator_actions.map((action) => (
                    <AdapterActionButton
                      key={action}
                      binding={resolveActionBinding(action)}
                    />
                  ))}
                  {"native_status" in selectedModule ? (
                    <>
                      <button
                        type="button"
                        onClick={() => runContractAction(selectedModuleAction("inspect_native_status"), "adapters")}
                        disabled={operatorPending || !selectedModuleAction("inspect_native_status")?.command}
                        className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                      >
                        inspect native
                      </button>
                      {nativeLastCommand?.target === selectedModule.name ? (
                        <button
                          type="button"
                          onClick={() => runContractAction(nativeAction("replay_last"), "adapters")}
                          disabled={operatorPending || !nativeAction("replay_last")?.command}
                          className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                        >
                          replay native
                        </button>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => {
                          const command = selectedModuleAction("focus_native")?.command;
                          if (!command) return;
                          runQuickCommand(command);
                        }}
                        disabled={operatorPending || !selectedModuleAction("focus_native")?.command}
                        className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                      >
                        native focus
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          const command = selectedModuleAction("inspect_native")?.command;
                          if (!command) return;
                          runQuickCommand(command);
                        }}
                        disabled={operatorPending || !selectedModuleAction("inspect_native")?.command}
                        className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                      >
                        native inspect
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          const command = selectedModuleAction("show_module")?.command;
                          if (!command) return;
                          runQuickCommand(command);
                        }}
                        disabled={operatorPending || !selectedModuleAction("show_module")?.command}
                        className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                      >
                        open module
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          const command = selectedModuleAction("fill_native_replay")?.command;
                          if (!command) return;
                          setOperatorCommand(command);
                        }}
                        disabled={operatorPending || !selectedModuleAction("fill_native_replay")?.command}
                        className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                      >
                        fill native cmd
                      </button>
                    </>
                  ) : null}
                </div>
              </div>
            ) : (
              <span className="text-xs text-muted-foreground">No modules exposed</span>
            )}
          </div>
        </section>

        <section className={paneClass("runtime")}>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Targets
          </div>
          <div className="rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Runtime targets
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {runtimeTargets.length ? runtimeTargets.map((target) => (
                <span
                  key={target}
                  className="rounded-full border border-violet-300/80 bg-violet-50 px-2.5 py-1 text-xs text-violet-700"
                >
                  {target}
                </span>
              )) : (
                <span className="text-xs text-muted-foreground">No runtime targets declared</span>
              )}
            </div>
            <div className="mt-4 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Kernel languages
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {runtimeLanguages.length ? runtimeLanguages.map((language) => (
                <span
                  key={language}
                  className="rounded-full border border-orange-300/80 bg-orange-50 px-2.5 py-1 text-xs text-orange-700"
                >
                  {language}
                </span>
              )) : (
                <span className="text-xs text-muted-foreground">No implementation languages declared</span>
              )}
            </div>
          </div>
        </section>

        <section className={paneClass("adapters")}>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Bridge control
          </div>
          <div className="grid gap-3 rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="grid gap-2 md:grid-cols-2">
              <Row label="Adapter" value={selectedBridge?.adapter ?? runtimeControl?.active_adapter ?? "unset"} />
              <Row label="Health" value={selectedBridge?.health ?? "unknown"} />
              <Row label="Status" value={selectedBridge?.status ?? "unknown"} />
              <Row label="Maintenance" value={runtimeControl?.maintenance_mode?.enabled ? "enabled" : "off"} />
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => runContractAction(selectedBridgeAction("inspect_bridge"), "adapters")}
                disabled={operatorPending || !selectedBridgeAction("inspect_bridge")?.command}
                className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
              >
                inspect
              </button>
              {actionAllowed(selectedBridgeAction("restart_bridge")) ? (
                <>
                  <button
                    type="button"
                    onClick={() => runContractAction(selectedBridgeAction("restart_bridge"), "adapters")}
                    disabled={operatorPending || !selectedBridgeAction("restart_bridge")?.command}
                    className="rounded-full border border-cyan-300/80 bg-cyan-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-cyan-700 transition-colors hover:bg-cyan-100"
                  >
                    restart
                  </button>
                  <button
                    type="button"
                    onClick={() => runContractAction(selectedBridgeAction("mark_bridge_fault"), "faults")}
                    disabled={operatorPending || !selectedBridgeAction("mark_bridge_fault")?.command}
                    className="rounded-full border border-rose-300/80 bg-rose-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-rose-700 transition-colors hover:bg-rose-100"
                  >
                    mark fault
                  </button>
                  <button
                    type="button"
                    onClick={() => runContractAction(selectedBridgeAction("clear_bridge_fault"), "faults")}
                    disabled={operatorPending || !selectedBridgeAction("clear_bridge_fault")?.command}
                    className="rounded-full border border-emerald-300/80 bg-emerald-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-emerald-700 transition-colors hover:bg-emerald-100"
                  >
                    clear fault
                  </button>
                </>
              ) : selectedBridgeAction("restart_bridge") ? (
                <span className="text-xs text-muted-foreground">
                  {actionRestrictionReason(selectedBridgeAction("restart_bridge"))}
                </span>
              ) : null}
            </div>
          </div>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Runtime adapter
          </div>
          <div className="rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                Adapter API
              </span>
              <span className="font-medium text-foreground">
                v{adapterContract?.api_version ?? 0}
              </span>
            </div>
            <div className="mt-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Transport
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {adapterTransports.length ? adapterTransports.map((transport) => (
                <span
                  key={transport}
                  className="rounded-full border border-emerald-300/80 bg-emerald-50 px-2.5 py-1 text-xs text-emerald-700"
                >
                  {transport}
                </span>
              )) : (
                <span className="text-xs text-muted-foreground">No adapter transport declared</span>
              )}
            </div>
            <div className="mt-4 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Control plane
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {adapterControlPlane.length ? adapterControlPlane.map((item) => (
                <span
                  key={item}
                  className="rounded-full border border-cyan-300/80 bg-cyan-50 px-2.5 py-1 text-xs text-cyan-700"
                >
                  {item}
                </span>
              )) : (
                <span className="text-xs text-muted-foreground">No control plane declared</span>
              )}
            </div>
            <div className="mt-4 grid gap-2 rounded-lg border border-border/70 bg-slate-50/70 p-3">
              <Row label="Default" value={adapterContract?.default_adapter ?? "unknown"} />
              <Row
                label="Hot swap"
                value={adapterContract?.supports_hot_swap ? "supported" : "planned"}
              />
              <Row
                label="Active"
                value={runtimeControl?.active_adapter ?? "unset"}
              />
            </div>
          </div>
        </section>

        <section className={paneClass("control_plane")}>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Operator console
          </div>
          <div className="rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                Console API
              </span>
              <span className="font-medium text-foreground">
                v{operatorConsole?.api_version ?? 0}
              </span>
            </div>
            <div className="mt-4 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Panes
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {(operatorConsole?.panes ?? []).map((pane) => (
                <span
                  key={pane}
                  className="rounded-full border border-slate-300/80 bg-slate-100 px-2.5 py-1 text-xs text-slate-700"
                >
                  {pane}
                </span>
              ))}
            </div>
            <div className="mt-4 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Telemetry
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {(operatorConsole?.telemetry ?? []).map((signal) => (
                <span
                  key={signal}
                  className="rounded-full border border-indigo-300/80 bg-indigo-50 px-2.5 py-1 text-xs text-indigo-700"
                >
                  {signal}
                </span>
              ))}
            </div>
            {runtimeControl?.adapter_failover_order?.length ? (
              <>
                <div className="mt-4 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  Failover order
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {runtimeControl.adapter_failover_order.map((adapter) => (
                    <span
                      key={adapter}
                      className="rounded-md border border-slate-300/80 bg-slate-950 px-2.5 py-1 text-[11px] text-slate-100"
                    >
                      {adapter}
                    </span>
                  ))}
                </div>
              </>
            ) : null}
            <div className="mt-4 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Embedded transports
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {(operatorConsole?.embedded_transports ?? []).map((transport) => (
                <span
                  key={transport}
                  className="rounded-full border border-orange-300/80 bg-orange-50 px-2.5 py-1 text-xs text-orange-700"
                >
                  {transport}
                </span>
              ))}
            </div>
          </div>
        </section>

        <section className={paneClass("adapters")}>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Runtime bridges
          </div>
          <div className="space-y-3 rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-lg border border-emerald-200/70 bg-emerald-50/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-emerald-700">Ready bridges</div>
                <div className="mt-2 text-lg font-semibold text-emerald-950">
                  {runtimeBridges.filter((bridge) => bridge.health === "ready").length}
                </div>
              </div>
              <div className="rounded-lg border border-rose-200/70 bg-rose-50/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-rose-700">Faulted bridges</div>
                <div className="mt-2 text-lg font-semibold text-rose-950">
                  {runtimeBridges.filter((bridge) => bridge.health === "fault").length}
                </div>
              </div>
              <div className="rounded-lg border border-amber-200/70 bg-amber-50/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-amber-700">Active adapter</div>
                <div className="mt-2 text-sm font-semibold text-amber-950">
                  {runtimeControl?.active_adapter ?? "unset"}
                </div>
              </div>
              <div className="rounded-lg border border-slate-200/70 bg-slate-50/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-slate-600">Failover chain</div>
                <div className="mt-2 text-sm font-semibold text-slate-900">
                  {runtimeControl?.adapter_failover_order?.length ?? 0}
                </div>
              </div>
            </div>
            {runtimeBridges.length ? runtimeBridges.map((bridge) => (
              <div
                key={bridge.adapter}
                className={cn(
                  "rounded-xl border px-3 py-3 shadow-sm",
                  selectedBridge?.adapter === bridge.adapter
                    ? "border-slate-900/20 bg-slate-100/90"
                    : "border-border/70 bg-slate-50/70",
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium text-foreground">{bridge.adapter}</div>
                  <span
                    className={cn(
                      "rounded-full border px-2 py-0.5 text-[11px]",
                      bridge.health === "ready"
                        ? "border-emerald-300/80 bg-emerald-50 text-emerald-700"
                        : bridge.health === "fault"
                          ? "border-rose-300/80 bg-rose-50 text-rose-700"
                          : "border-amber-300/80 bg-amber-50 text-amber-700",
                    )}
                  >
                    {bridge.health}
                  </span>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {bridge.backend_kind} · {bridge.entrypoint}
                </div>
                <div className="mt-3 grid gap-2 md:grid-cols-4">
                  <Row label="Stage" value={bridge.runtime_stage} />
                  <Row label="Mode" value={bridge.runtime_mode} />
                  <Row label="ABI" value={bridge.abi} />
                  <Row label="Artifact" value={bridge.manifest ?? bridge.entrypoint} />
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <ConsoleBadge
                    label="status"
                    value={bridge.status}
                    tone={bridge.status === "active" ? "emerald" : "slate"}
                  />
                  <ConsoleBadge
                    label="board"
                    value={bridge.board_capable ? "capable" : "hosted"}
                    tone={bridge.board_capable ? "amber" : "slate"}
                  />
                  {bridge.runtime_stage ? (
                    <ConsoleBadge
                      label="stage"
                      value={bridge.runtime_stage}
                      tone={bridge.runtime_stage === "manifested" ? "emerald" : "amber"}
                    />
                  ) : null}
                  {bridge.abi ? (
                    <ConsoleBadge label="abi" value={bridge.abi} tone="slate" />
                  ) : null}
                  {bridge.runtime_mode ? (
                    <ConsoleBadge label="mode" value={bridge.runtime_mode} tone="slate" />
                  ) : null}
                </div>
                {bridge.manifest || bridge.status_symbol || bridge.build_hint ? (
                  <div className="mt-3 grid gap-2 rounded-md border border-slate-200/80 bg-white/80 p-3 text-xs">
                    {bridge.manifest ? (
                      <Row label="Manifest" value={bridge.manifest} />
                    ) : null}
                    {bridge.runtime_mode ? (
                      <Row label="Runtime mode" value={bridge.runtime_mode} />
                    ) : null}
                    {bridge.status_symbol ? (
                      <Row label="Status symbol" value={bridge.status_symbol} />
                    ) : null}
                    {bridge.build_hint ? (
                      <Row label="Build hint" value={bridge.build_hint} />
                    ) : null}
                  </div>
                ) : null}
                <div className="mt-3 flex flex-wrap gap-2">
                  <AdapterActionButton
                    binding={{
                      ...resolveActionBinding("restart_bridge"),
                      onTrigger: () => runQuickCommand(`restart-bridge ${bridge.adapter}`),
                    }}
                  />
                  <AdapterActionButton
                    binding={{
                      ...resolveActionBinding("record_fault"),
                      onTrigger: () => runQuickCommand(`record-fault fault ${bridge.adapter}`),
                    }}
                  />
                  {bridge.health === "fault" ? (
                    <AdapterActionButton
                      binding={{
                        ...resolveActionBinding("clear_fault"),
                        onTrigger: () => runQuickCommand(`clear-fault ${bridge.adapter}`),
                      }}
                    />
                  ) : null}
                </div>
                {bridge.last_error ? (
                  <div className="mt-2 rounded-md border border-rose-300/60 bg-rose-50 px-2.5 py-2 text-[11px] text-rose-800">
                    {bridge.last_error}
                  </div>
                ) : null}
              </div>
            )) : (
              <div className="text-xs text-muted-foreground">
                No runtime bridges registered.
              </div>
            )}
          </div>
        </section>

        <section className={paneClass("adapters")}>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Board attachment
          </div>
          <div className="grid gap-2 rounded-xl border border-border/70 bg-background/80 p-3">
            <Row label="Target" value={boardSnapshot?.target ?? "unknown"} />
            <Row label="Attach" value={boardSnapshot?.attached ? "attached" : "detached"} />
            <Row
              label="Transport"
              value={boardSnapshot?.transport ?? boardSnapshot?.preferred_transport ?? "unset"}
            />
            <Row label="Port" value={boardSnapshot?.port ?? "not bound"} />
            <Row
              label="Supervisor"
              value={runtimeControl?.fault_posture.supervisor ?? "unknown"}
            />
            <Row
              label="Maintenance"
              value={runtimeControl?.maintenance_mode?.enabled ? "enabled" : "off"}
            />
            <Row
              label="Runtime mode"
              value={boardSnapshot?.runtime_mode ?? "unprobed"}
            />
            <Row label="Health" value={boardSnapshot?.health ?? "unknown"} />
            <Row
              label="Bridge artifact"
              value={boardSnapshot?.bridge_artifact ?? "none"}
            />
            <div className="grid gap-2 rounded-md border border-slate-200/80 bg-white/80 px-2.5 py-2">
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                Attach controls
              </div>
              <label className="grid gap-1 text-[11px] uppercase tracking-[0.12em] text-slate-500">
                <span>Transport</span>
                <select
                  value={selectedBoardTransport ?? ""}
                  onChange={(event) => onSelectBoardTransport?.(event.target.value || null)}
                  className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-900"
                >
                  <option value="">auto</option>
                  {Array.from(new Set([
                    ...(operatorConsole?.embedded_transports ?? []),
                    ...([boardSnapshot?.preferred_transport].filter(Boolean) as string[]),
                    ...([boardSnapshot?.transport].filter(Boolean) as string[]),
                  ])).map((transport) => (
                    <option key={transport} value={transport}>
                      {transport}
                    </option>
                  ))}
                </select>
              </label>
              <label className="grid gap-1 text-[11px] uppercase tracking-[0.12em] text-slate-500">
                <span>Port</span>
                <select
                  value={selectedBoardPort ?? ""}
                  onChange={(event) => onSelectBoardPort?.(event.target.value || null)}
                  className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-900"
                >
                  <option value="">auto-detect</option>
                  {(boardSnapshot?.available_ports ?? []).map((port) => (
                    <option key={port} value={port}>
                      {port}
                    </option>
                  ))}
                </select>
              </label>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => onAttachBoard?.({
                    transport: selectedBoardTransport ?? null,
                    port: selectedBoardPort ?? null,
                  })}
                  className="rounded-md border border-slate-900 bg-slate-900 px-2.5 py-1.5 text-[11px] uppercase tracking-[0.12em] text-white transition-colors hover:bg-slate-800"
                >
                  Attach board
                </button>
                <button
                  type="button"
                  onClick={() => runQuickCommand("detach-board")}
                  className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-[11px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
                >
                  Detach board
                </button>
              </div>
            </div>
            {boardSnapshot?.available_ports?.length ? (
              <div className="rounded-md border border-slate-200/80 bg-white/80 px-2.5 py-2">
                <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                  Candidate ports
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {(boardSnapshot?.available_ports ?? []).slice(0, 6).map((port) => (
                    <button
                      key={port}
                      type="button"
                      onClick={() => onSelectBoardPort?.(port)}
                      className={cn(
                        "rounded-full border px-2 py-0.5 text-[11px] transition-colors",
                        selectedBoardPort === port
                          ? "border-slate-900 bg-slate-900 text-white"
                          : "border-slate-300/80 bg-slate-50 text-slate-700 hover:bg-slate-100",
                      )}
                    >
                      {port}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            {boardSnapshot?.last_error ? (
              <div className="rounded-md border border-rose-300/60 bg-rose-50 px-2.5 py-2 text-[11px] text-rose-800">
                {boardSnapshot.last_error}
              </div>
            ) : null}
          </div>
        </section>

        <section className={paneClass("adapters")}>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Adapter registry
          </div>
          <div className="space-y-2 rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="flex flex-wrap gap-2">
              {runtimeAdapters.map((adapter) => (
                <button
                  key={adapter.name}
                  type="button"
                  onClick={() => onSelectAdapter(adapter.name)}
                  className={cn(
                    "rounded-full border px-2.5 py-1 text-[11px] transition-colors",
                    selectedAdapter?.name === adapter.name
                      ? "border-slate-900 bg-slate-900 text-white"
                      : "border-slate-300/80 bg-white text-slate-700 hover:bg-slate-50",
                  )}
                >
                  {adapter.name}
                </button>
              ))}
            </div>
            {runtimeAdapters.length ? runtimeAdapters.map((adapter) => (
              <div
                key={adapter.name}
                className={cn(
                  "rounded-xl border px-3 py-2",
                  selectedAdapter?.name === adapter.name
                    ? "border-slate-900/20 bg-slate-100/90"
                    : "border-border/70 bg-slate-50/70",
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium text-foreground">{adapter.display_name}</div>
                  <span className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[11px] text-slate-600">
                    {adapter.maturity}
                  </span>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {adapter.implementation_language} · {adapter.transport} · {adapter.target_class}
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {adapter.capabilities.map((capability) => (
                    <span
                      key={capability}
                      className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[11px] text-slate-700"
                    >
                      {capability}
                    </span>
                  ))}
                </div>
                {selectedAdapter?.name === adapter.name ? (
                  <div className="mt-3 grid gap-2 rounded-md border border-slate-300/70 bg-white/80 p-3 text-xs">
                    <Row label="Boot posture" value={adapter.enabled_by_default ? "auto" : "manual"} />
                    <Row label="Operator path" value={adapter.notes || "No notes"} />
                    <Row label="Active route" value={runtimeControl?.active_adapter === adapter.name ? "selected" : "standby"} />
                    <Row label="Runtime stage" value={adapter.runtime_stage ?? "planned"} />
                    <Row label="ABI" value={adapter.abi ?? "unspecified"} />
                    <Row
                      label="Bridge health"
                      value={
                        runtimeBridges.find((bridge) => bridge.adapter === adapter.name)?.health
                        ?? "unknown"
                      }
                    />
                    {adapter.runtime_manifest ? (
                      <Row label="Manifest" value={adapter.runtime_manifest} />
                    ) : null}
                    {adapter.status_symbol ? (
                      <Row label="Status symbol" value={adapter.status_symbol} />
                    ) : null}
                    {adapter.bootstrap_artifact ? (
                      <Row label="Bootstrap" value={adapter.bootstrap_artifact} />
                    ) : null}
                    {adapter.build_hint ? (
                      <Row label="Build hint" value={adapter.build_hint} />
                    ) : null}
                    <div className="mt-1">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                        Suggested actions
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {adapter.operator_actions.map((action) => (
                          <AdapterActionButton
                            key={action}
                            binding={resolveActionBinding(action)}
                          />
                        ))}
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            )) : (
              <div className="text-xs text-muted-foreground">
                No runtime adapters registered.
              </div>
            )}
          </div>
        </section>

        <section className={paneClass("runtime")}>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Tools
          </div>
          <div className="flex flex-wrap gap-2 rounded-xl border border-border/70 bg-background/80 p-3">
            {toolRows.length ? toolRows.map((tool) => (
              <span
                key={tool}
                className="rounded-full border border-sky-300/80 bg-sky-50 px-2.5 py-1 text-xs text-sky-700"
              >
                {tool}
              </span>
            )) : (
              <span className="text-xs text-muted-foreground">No tool contract exposed</span>
            )}
          </div>
        </section>

        <section className={paneClass("runtime")}>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Runtime
          </div>
          <div className="grid gap-2 rounded-xl border border-border/70 bg-background/80 p-3">
            <Row
              label="Streaming"
              value={executionContract?.supports_streaming ? "enabled" : "off"}
            />
            <Row
              label="Background"
              value={executionContract?.supports_background ? "enabled" : "off"}
            />
            <Row
              label="Engine restart"
              value={runtimeCapabilities?.can_restart_engine ? "available" : "n/a"}
            />
            <Row
              label="Open logs"
              value={runtimeCapabilities?.can_open_logs ? "available" : "n/a"}
            />
            <Row
              label="Diag modules"
              value={`${diagnostics?.snapshot.module_count ?? runtimeModules.length}`}
            />
            <Row
              label="Diag bridges"
              value={`${diagnostics?.snapshot.bridge_count ?? runtimeBridges.length}`}
            />
            <Row
              label="Diag gate"
              value={diagnostics?.snapshot.execution_gate ?? runtimeControl?.execution_gate?.state ?? "open"}
            />
            <Row label="Diag phase" value={diagPhase ?? "idle"} />
            <Row label="Diag iter" value={`${diagIteration ?? 0}`} />
            <Row label="Tool wait" value={`${diagPendingToolCalls}`} />
            <Row label="Subagents" value={`${diagSubagentWorkers}`} />
            <Row
              label="Board"
              value={boardSnapshot?.attached ? "attached" : "detached"}
            />
            <Row
              label="Board mode"
              value={boardSnapshot?.runtime_mode ?? "unprobed"}
            />
            <Row
              label="Board health"
              value={boardSnapshot?.health ?? "unknown"}
            />
            <Row
              label="Native health"
              value={nativeSnapshot?.health ?? "unknown"}
            />
            <Row
              label="Native queue"
              value={`${nativeSnapshot?.queue_depth ?? nativeSnapshot?.command_depth ?? 0}`}
            />
            <Row
              label="Native modules"
              value={`${nativeSnapshot?.module_count ?? nativeModuleEntries.length}`}
            />
            <Row
              label="Native bridge"
              value={nativeSnapshot?.bridge_artifact ?? "none"}
            />
          </div>
          <div className="grid gap-3 rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                Native control
              </div>
              <ConsoleBadge
                label="queue"
                value={`${nativeSnapshot?.queue_depth ?? nativeSnapshot?.command_depth ?? 0}`}
                tone={(nativeSnapshot?.queue_depth ?? nativeSnapshot?.command_depth) ? "amber" : "slate"}
              />
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              <Row label="Last target" value={nativeLastCommand?.target ?? "none"} />
              <Row label="Last action" value={nativeLastCommand?.action ?? "none"} />
              <Row label="Last command" value={lastNativeCommand} />
              <Row label="Last status" value={lastNativeStatus} />
              <Row label="Last code" value={String(lastNativeCode)} />
              <Row label="Last value" value={nativeLastCommand?.value || "none"} />
              <Row label="Artifact" value={nativeLastCommand?.artifact ?? nativeSnapshot?.bridge_artifact ?? "none"} />
              <Row label="Module focus" value={runtimeControl?.module_focus ?? "none"} />
              <Row label="Command backlog" value={`${nativeSnapshot?.command_depth ?? 0}`} />
              <Row label="Updated" value={lastNativeUpdated ? formatKernelTimestamp(lastNativeUpdated) : "none"} />
            </div>
            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500">Native modules</div>
              <div className="flex flex-wrap gap-2">
                {nativeModuleEntries.length ? nativeModuleEntries.slice(0, 8).map(([name, state]) => (
                  <button
                    key={name}
                    type="button"
                    onClick={() => runContractAction(state?.actions?.find((action) => action.id === "inspect_native_module"), "modules")}
                    disabled={operatorPending || !state?.actions?.find((action) => action.id === "inspect_native_module")?.command}
                    className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                  >
                    {name}:{state?.status ?? "unknown"}
                  </button>
                )) : (
                  <span className="text-xs text-muted-foreground">No native modules observed.</span>
                )}
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500">Recent commands</div>
              <div className="flex flex-wrap gap-2">
                {nativeRecentCommands.length ? nativeRecentCommands.map((command, index) => (
                  <button
                    key={`${command.updated_at_ms ?? "native"}-${command.target ?? "target"}-${command.action ?? index}`}
                    type="button"
                    onClick={() => {
                      const replayAction = command.actions?.find((action) => action.id === "replay_recent_command");
                      runContractAction(replayAction, "adapters");
                    }}
                    disabled={operatorPending || !command.actions?.some((action) => action.id === "replay_recent_command" && action.command)}
                    className="rounded-full border border-slate-300/80 bg-slate-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-100"
                  >
                    {(command.target ?? "target")}:{(command.action ?? "action")}:{(command.status ?? "queued")}:{command.queue_depth ?? 0}
                  </button>
                )) : (
                  <span className="text-xs text-muted-foreground">No recent native commands.</span>
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => runContractAction(nativeAction("native_status"), "adapters")}
                disabled={operatorPending || !nativeAction("native_status")?.command}
                className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
              >
                inspect native
              </button>
              <button
                type="button"
                onClick={() => runContractAction(nativeAction("native_last_command"), "adapters")}
                disabled={operatorPending || !nativeAction("native_last_command")?.command}
                className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
              >
                last command
              </button>
              <button
                type="button"
                onClick={() => runContractAction(nativeAction("native_modules"), "modules")}
                disabled={operatorPending || !nativeAction("native_modules")?.command}
                className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
              >
                native modules
              </button>
              {nativeLastCommand?.target && nativeLastCommand?.action ? (
                <>
                  <button
                    type="button"
                    onClick={() => runContractAction(nativeAction("focus_last_target"), "modules")}
                    disabled={operatorPending || !nativeAction("focus_last_target")?.command}
                    className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                  >
                    focus last target
                  </button>
                  <button
                    type="button"
                    onClick={() => runContractAction(nativeAction("replay_last"), "adapters")}
                    disabled={operatorPending || !nativeAction("replay_last")?.command}
                    className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                  >
                    replay last
                  </button>
                  <button
                    type="button"
                    onClick={() => runContractAction(nativeAction("open_last_target"), "modules")}
                    disabled={operatorPending || !nativeAction("open_last_target")?.command}
                    className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                  >
                    open target
                  </button>
                </>
              ) : faultAction("clear_faults") ? (
                <span className="text-xs text-muted-foreground">
                  {actionRestrictionReason(faultAction("clear_faults"))}
                </span>
              ) : null}
              {selectedModule?.name ? (
                <>
                  <button
                    type="button"
                    onClick={() => runContractAction(selectedModuleAction("focus_native"), "modules")}
                    disabled={operatorPending || !selectedModuleAction("focus_native")?.command}
                    className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                  >
                    focus selected
                  </button>
                  <button
                    type="button"
                    onClick={() => runContractAction(selectedModuleAction("inspect_native"), "modules")}
                    disabled={operatorPending || !selectedModuleAction("inspect_native")?.command}
                    className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                  >
                    inspect selected
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const command = selectedModuleAction("fill_native_inspect")?.command;
                      if (!command) return;
                      setOperatorCommand(command);
                    }}
                    disabled={operatorPending || !selectedModuleAction("fill_native_inspect")?.command}
                    className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                  >
                    fill selected inspect
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const command = selectedModuleAction("fill_native_replay")?.command;
                      if (!command) return;
                      setOperatorCommand(command);
                    }}
                    disabled={operatorPending || !selectedModuleAction("fill_native_replay")?.command}
                    className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                  >
                    fill selected replay
                  </button>
                </>
              ) : null}
            </div>
          </div>
          <div className="grid gap-3 rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                Runtime topology
              </div>
              <ConsoleBadge
                label="lane"
                value={runtimeTopology?.scheduler?.preferred_lane ?? scheduler?.preferred_lane ?? "interactive"}
                tone="slate"
              />
            </div>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-lg border border-emerald-200/70 bg-emerald-50/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-emerald-700">Preferred lane</div>
                <div className="mt-2 text-sm font-semibold text-emerald-950">
                  {runtimeTopology?.scheduler?.preferred_lane ?? scheduler?.preferred_lane ?? "interactive"}
                </div>
              </div>
              <div className="rounded-lg border border-sky-200/70 bg-sky-50/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-sky-700">Workers</div>
                <div className="mt-2 text-lg font-semibold text-sky-950">
                  {runtimeTopology?.workers?.length ?? workers.length}
                </div>
              </div>
              <div className="rounded-lg border border-fuchsia-200/70 bg-fuchsia-50/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-fuchsia-700">Module focus</div>
                <div className="mt-2 text-sm font-semibold text-fuchsia-950">
                  {runtimeControl?.module_focus ?? selectedModule?.name ?? "none"}
                </div>
              </div>
              <div className="rounded-lg border border-amber-200/70 bg-amber-50/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-amber-700">Dispatch queue</div>
                <div className="mt-2 text-lg font-semibold text-amber-950">
                  {dispatchQueue?.depth ?? 0}
                </div>
              </div>
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              <Row label="Adapters" value={`${runtimeTopologyAdapters.length}`} />
              <Row label="Modules" value={`${runtimeTopologyModules.length}`} />
              <Row label="Lanes" value={`${runtimeTopologyLanes.length}`} />
              <Row label="Workers" value={`${runtimeTopology?.workers?.length ?? workers.length}`} />
            </div>
            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500">Adapters</div>
              <div className="flex flex-wrap gap-2">
                {runtimeTopologyAdapters.length ? runtimeTopologyAdapters.map((adapter) => (
                  <button
                    key={adapter.name}
                    type="button"
                    onClick={() => {
                      onSelectAdapter(adapter.name);
                      runContractAction(adapter.actions?.find((action) => action.id === "inspect_adapter"), "adapters");
                    }}
                    disabled={operatorPending || !adapter.actions?.find((action) => action.id === "inspect_adapter")?.command}
                    className="rounded-full border border-emerald-300/80 bg-emerald-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-emerald-700 transition-colors hover:bg-emerald-100"
                  >
                    {adapter.name}
                  </button>
                )) : (
                  <span className="text-xs text-muted-foreground">No adapter topology exposed.</span>
                )}
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500">Lanes</div>
              <div className="flex flex-wrap gap-2">
                {runtimeTopologyLanes.length ? runtimeTopologyLanes.map((lane) => (
                  <button
                    key={lane.id}
                    type="button"
                    onClick={() => runContractAction(lane.actions?.find((action) => action.id === "open_lane"), "runtime")}
                    disabled={operatorPending || !lane.actions?.find((action) => action.id === "open_lane")?.command}
                    className="rounded-full border border-blue-300/80 bg-blue-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-blue-700 transition-colors hover:bg-blue-100"
                  >
                    {lane.id}
                  </button>
                )) : (
                  <span className="text-xs text-muted-foreground">No lane topology exposed.</span>
                )}
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500">Modules</div>
              <div className="flex flex-wrap gap-2">
                {runtimeTopologyModules.length ? runtimeTopologyModules.map((module) => (
                  <div key={module.name} className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => {
                        onSelectModule(module.name);
                        runContractAction(module.actions?.find((action) => action.id === "show_module"), "modules");
                      }}
                      disabled={operatorPending || !module.actions?.find((action) => action.id === "show_module")?.command}
                      className={cn(
                        "rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] transition-colors",
                        module.native_status === "fault"
                          ? "border-rose-300/80 bg-rose-50 text-rose-700 hover:bg-rose-100"
                          : module.native_status === "busy"
                            ? "border-amber-300/80 bg-amber-50 text-amber-700 hover:bg-amber-100"
                            : module.native_status
                              ? "border-fuchsia-300/80 bg-fuchsia-50 text-fuchsia-700 hover:bg-fuchsia-100"
                              : "border-slate-300/80 bg-slate-50 text-slate-700 hover:bg-slate-100",
                      )}
                    >
                      {module.name}
                    </button>
                    {module.native_status ? (
                      <button
                        type="button"
                        onClick={() => runContractAction(module.actions?.find((action) => action.id === "focus_native"), "modules")}
                        disabled={operatorPending || !module.actions?.find((action) => action.id === "focus_native")?.command}
                        className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                      >
                        inspect
                      </button>
                    ) : null}
                  </div>
                )) : (
                  <span className="text-xs text-muted-foreground">No module topology exposed.</span>
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => runContractAction(runtimeTopologyAction("inspect_runtime"), "runtime")}
                disabled={operatorPending || !runtimeTopologyAction("inspect_runtime")?.command}
                className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
              >
                inspect runtime
              </button>
              <button
                type="button"
                onClick={() => runContractAction(runtimeTopologyAction("runtime_orchestration"), "runtime")}
                disabled={operatorPending || !runtimeTopologyAction("runtime_orchestration")?.command}
                className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
              >
                orchestration
              </button>
            </div>
          </div>
          <div className="grid gap-3 rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                Embedded topology
              </div>
              <ConsoleBadge
                label="board"
                value={boardSnapshot?.attached ? "attached" : "detached"}
                tone={boardSnapshot?.attached ? "emerald" : "amber"}
              />
            </div>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-lg border border-amber-200/70 bg-amber-50/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-amber-700">Board health</div>
                <div className="mt-2 text-sm font-semibold text-amber-950">
                  {boardSnapshot?.health ?? "unknown"}
                </div>
              </div>
              <div className="rounded-lg border border-slate-200/70 bg-slate-50/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-slate-600">Runtime mode</div>
                <div className="mt-2 text-sm font-semibold text-slate-950">
                  {boardSnapshot?.runtime_mode ?? "userland"}
                </div>
              </div>
              <div className="rounded-lg border border-cyan-200/70 bg-cyan-50/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-cyan-700">Known ports</div>
                <div className="mt-2 text-lg font-semibold text-cyan-950">
                  {embeddedPorts.length}
                </div>
              </div>
              <div className="rounded-lg border border-fuchsia-200/70 bg-fuchsia-50/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-fuchsia-700">Bridge artifact</div>
                <div className="mt-2 text-sm font-semibold text-fuchsia-950">
                  {boardSnapshot?.bridge_artifact ?? "none"}
                </div>
              </div>
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              <Row label="Target" value={boardSnapshot?.target ?? embeddedTargetHint ?? "host"} />
              <Row label="Transport" value={boardSnapshot?.transport ?? boardSnapshot?.preferred_transport ?? "unset"} />
              <Row label="Runtime mode" value={boardSnapshot?.runtime_mode ?? "userland"} />
              <Row label="Health" value={boardSnapshot?.health ?? "unknown"} />
              <Row label="Port" value={boardSnapshot?.port ?? "none"} />
            </div>
            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500">Available ports</div>
              <div className="flex flex-wrap gap-2">
                {embeddedPorts.length ? embeddedPorts.map((port) => (
                  <button
                    key={port}
                    type="button"
                    onClick={() => {
                      onSelectPane(embeddedTopologyAction("board_status")?.pane ?? "adapters");
                      onSelectBoardPort?.(port);
                      runContractAction(embeddedTopologyAction("board_status"), "adapters");
                    }}
                    disabled={operatorPending || !embeddedTopologyAction("board_status")?.command}
                    className="rounded-full border border-amber-300/80 bg-amber-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-amber-700 transition-colors hover:bg-amber-100"
                  >
                    {port}
                  </button>
                )) : (
                  <span className="text-xs text-muted-foreground">No serial ports discovered.</span>
                )}
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-lg border border-slate-200/80 bg-white/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500">Control posture</div>
                <div className="mt-2 text-sm font-semibold text-slate-950">
                  {allowsPrivilegedControls ? "root-enabled" : "observe-only"}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {allowsPrivilegedControls ? "board attachment and recovery actions are writable" : "this shell can inspect board state but not mutate hardware posture"}
                </div>
              </div>
              <div className="rounded-lg border border-amber-200/80 bg-amber-50/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-amber-700">Attach target</div>
                <div className="mt-2 text-sm font-semibold text-amber-950">
                  {boardSnapshot?.port ?? embeddedPorts[0] ?? "no-port"}
                </div>
                <div className="mt-1 text-xs text-amber-700/80">
                  transport {boardSnapshot?.transport ?? boardSnapshot?.preferred_transport ?? "unset"}
                </div>
              </div>
              <div className="rounded-lg border border-cyan-200/80 bg-cyan-50/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-cyan-700">Next action</div>
                <div className="mt-2 text-sm font-semibold text-cyan-950">
                  {boardSnapshot?.attached ? "stabilize board" : "attach board"}
                </div>
                <div className="mt-1 text-xs text-cyan-700/80">
                  {boardSnapshot?.attached ? "inspect runtime mode or refresh ports before switching" : "refresh ports first, then attach on the target transport"}
                </div>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => runContractAction(embeddedTopologyAction("inspect_embedded"), "runtime")}
                disabled={operatorPending || !embeddedTopologyAction("inspect_embedded")?.command}
                className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
              >
                inspect embedded
              </button>
              <button
                type="button"
                onClick={() => runContractAction(embeddedTopologyAction("refresh_board_ports"), "adapters")}
                disabled={operatorPending || !embeddedTopologyAction("refresh_board_ports")?.command}
                className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
              >
                refresh ports
              </button>
              <button
                type="button"
                onClick={() => runQuickCommand(boardSnapshot?.attached ? "board detach" : `board attach ${boardSnapshot?.port ?? embeddedPorts[0] ?? ""}`.trim())}
                disabled={operatorPending || !allowsPrivilegedControls || (!boardSnapshot?.attached && !boardSnapshot?.port && !embeddedPorts.length)}
                className="rounded-full border border-amber-300/80 bg-amber-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-amber-700 transition-colors hover:bg-amber-100"
              >
                {boardSnapshot?.attached ? "detach board" : "attach board"}
              </button>
              <button
                type="button"
                onClick={() => runQuickCommand("board mode")}
                disabled={operatorPending}
                className="rounded-full border border-cyan-300/80 bg-cyan-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-cyan-700 transition-colors hover:bg-cyan-100"
              >
                board mode
              </button>
            </div>
            {!allowsPrivilegedControls ? (
              <div className="rounded-md border border-amber-200/80 bg-amber-50/80 px-3 py-2 text-[11px] text-amber-800">
                Board mutation is locked in this shell. Promote to a root-capable shell to attach, detach, or recover hardware targets.
              </div>
            ) : null}
          </div>
          <div className="rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Execution lanes
            </div>
            {executionLanes.length ? (
              <div className="space-y-2">
                {executionLanes.map((lane) => (
                  <div
                    key={lane.id}
                    className="rounded-md border border-slate-200/80 bg-slate-50/80 px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-700">
                        {lane.label}
                      </span>
                      <span className="text-[11px] text-slate-500">
                        {lane.mode} · {lane.state}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-slate-800">{lane.summary}</div>
                    {lane.id === "interactive" && diagPendingToolCalls > 0 ? (
                      <div className="mt-2 text-[11px] text-slate-500">
                        waiting on {diagPendingToolCalls} tool call(s)
                      </div>
                    ) : null}
                    {lane.id === "interactive" && (nativeSnapshot?.queue_depth ?? nativeSnapshot?.command_depth ?? 0) > 0 ? (
                      <div className="mt-1 text-[11px] text-fuchsia-700">
                        native queue pressure: {nativeSnapshot?.queue_depth ?? nativeSnapshot?.command_depth ?? 0} command(s)
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-muted-foreground">
                No execution lanes exposed.
              </div>
            )}
          </div>
          <div className="rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Runtime topology
            </div>
            <div className="mb-3 grid gap-2 rounded-md border border-slate-200/80 bg-white/80 p-3 text-xs">
              <Row
                label="Adapters"
                value={`${runtimeTopology?.adapters.length ?? runtimeAdapters.length}`}
              />
              <Row
                label="Modules"
                value={`${runtimeTopology?.modules.length ?? runtimeModules.length}`}
              />
              <Row
                label="Bridges"
                value={`${runtimeTopology?.bridges.length ?? runtimeBridges.length}`}
              />
              <Row
                label="Workers"
                value={`${runtimeTopology?.workers.length ?? workers.length}`}
              />
              <Row
                label="Queues"
                value={`${runtimeTopology?.scheduler.queues.length ?? schedulerQueues.length}`}
              />
              <Row
                label="Native queue"
                value={`${nativeSnapshot?.queue_depth ?? nativeSnapshot?.command_depth ?? 0}`}
              />
              <Row
                label="Board"
                value={boardSnapshot?.attached ? "attached" : "detached"}
              />
            </div>
          </div>
          <div className="rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Scheduler
            </div>
            <div className="mb-3 text-[11px] text-slate-500">
              {scheduler?.policy ?? "unspecified-policy"}
            </div>
            <div className="mb-3 grid gap-2 rounded-md border border-slate-200/80 bg-white/80 p-3 text-xs">
              <Row label="Preferred lane" value={scheduler?.preferred_lane ?? "interactive"} />
              <Row label="Dispatch priority" value={scheduler?.dispatch_priority ? "on" : "off"} />
              <Row label="Dispatch handoff" value={scheduler?.dispatch_handoff_lane ?? "none"} />
              <Row
                label="Drain background"
                value={scheduler?.background_drain_requested ? "requested" : "idle"}
              />
              <Row
                label="Active runtime"
                value={scheduler?.active_runtime?.adapter ?? "python-inprocess"}
              />
              <Row
                label="Runtime health"
                value={scheduler?.active_runtime?.health ?? "ready"}
              />
              <Row
                label="Native queue"
                value={`${nativeSnapshot?.queue_depth ?? nativeSnapshot?.command_depth ?? 0}`}
              />
            </div>
            {scheduler?.active_runtime ? (
              <div className="mb-3 grid gap-2 rounded-md border border-slate-200/80 bg-slate-50/80 p-3 text-xs">
                <Row label="Mode" value={scheduler.active_runtime.runtime_mode ?? "unknown"} />
                <Row label="Stage" value={scheduler.active_runtime.runtime_stage ?? "unknown"} />
                <Row label="Artifact" value={scheduler.active_runtime.artifact ?? "none"} />
              </div>
            ) : null}
            {schedulerQueues.length ? (
              <div className="space-y-2">
                {schedulerQueues.map((queue) => (
                  <div
                    key={queue.id}
                    className="rounded-md border border-slate-200/80 bg-slate-50/80 px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-700">
                        {queue.label}
                      </span>
                      <span className="text-[11px] text-slate-500">
                        depth {queue.depth} · {queue.state}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-slate-800">
                      {queue.lane} · {queue.job_class}
                    </div>
                    {queue.dispatch_contract ? (
                      <div className="mt-2 text-[11px] text-slate-500">
                        contract {queue.dispatch_contract.owner ?? "interactive"} · {queue.dispatch_contract.mode ?? "direct"} · {queue.dispatch_contract.lane ?? queue.lane}
                      </div>
                    ) : null}
                    {queue.state === "delegated" || queue.state === "handoff" ? (
                      <div className="mt-2 text-[11px] text-fuchsia-700">
                        orchestration handoff active
                      </div>
                    ) : null}
                    {typeof queue.pending_tool_calls === "number" || typeof queue.completed_tool_results === "number" ? (
                      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-500">
                        {typeof queue.pending_tool_calls === "number" ? (
                          <span>pending tools {queue.pending_tool_calls}</span>
                        ) : null}
                        {typeof queue.completed_tool_results === "number" ? (
                          <span>completed tools {queue.completed_tool_results}</span>
                        ) : null}
                      </div>
                    ) : null}
                    {queue.active_tasks?.length ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {queue.active_tasks.map((task) => (
                          <button
                            key={task}
                            type="button"
                            onClick={() => {
                              if (task.startsWith("dispatch:")) {
                                runContractAction(dispatchQueueAction("inspect_dispatch"), "runtime");
                                return;
                              }
                              if (queue.lane === "subagent") {
                                runContractAction(workerControls[0], "runtime");
                                return;
                              }
                              if (queue.lane === "sustained_goal") {
                                runContractAction(sessionControls[1], "runtime");
                                return;
                              }
                            }}
                            disabled={operatorPending}
                            className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[11px] text-slate-700 transition-colors hover:bg-slate-50"
                          >
                            {task}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-muted-foreground">
                No scheduler queues exposed.
              </div>
            )}
          </div>
          <div className="rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Workers
            </div>
            {workers.length ? (
              <div className="space-y-2">
                {workers.map((worker) => (
                  <div
                    key={worker.id}
                    className="rounded-md border border-slate-200/80 bg-slate-50/80 px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-700">
                        {worker.label}
                      </span>
                      <span className="text-[11px] text-slate-500">
                        {worker.kind} · {worker.state}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-slate-800">
                      {worker.lane} · {worker.summary}
                    </div>
                    {(worker.lane === "sustained_goal" || worker.lane === "subagent") && worker.tasks?.length ? (
                      <div className="mt-2 text-[11px] text-fuchsia-700">
                        {worker.lane === "sustained_goal" ? "goal handoff contract active" : "subagent handoff contract active"}
                      </div>
                    ) : null}
                    {worker.runtime_backend ? (
                      <div className="mt-2 grid gap-2 rounded-md border border-slate-200/80 bg-white/80 p-3 text-xs">
                        <Row label="Adapter" value={worker.runtime_backend.adapter ?? "unknown"} />
                        <Row label="Health" value={worker.runtime_backend.health ?? "unknown"} />
                        <Row label="Mode" value={worker.runtime_backend.runtime_mode ?? "unknown"} />
                        <Row label="Stage" value={worker.runtime_backend.runtime_stage ?? "unknown"} />
                      </div>
                    ) : null}
                    {worker.tasks?.length ? (
                      <div className="mt-2 space-y-2">
                        {worker.tasks.map((task) => (
                          <div
                            key={task.task_id}
                            className="rounded-md border border-slate-200/80 bg-white/80 px-2.5 py-2"
                          >
                            <div className="flex items-center justify-between gap-3 text-[11px]">
                              <span className="font-semibold uppercase tracking-[0.12em] text-slate-700">
                                {task.label}
                              </span>
                              <span className="text-slate-500">
                                {task.phase} · iter {task.iteration}
                              </span>
                            </div>
                            <div className="mt-1 text-xs text-slate-600">
                              {task.task_description}
                            </div>
                            {task.dispatch_contract ? (
                              <div className="mt-2 text-[11px] text-slate-500">
                                contract {task.dispatch_contract.owner ?? "interactive"} · {task.dispatch_contract.mode ?? "direct"} · {task.dispatch_contract.lane ?? worker.lane}
                              </div>
                            ) : null}
                            {task.actions?.length ? (
                              <div className="mt-2 flex flex-wrap gap-2">
                                {task.actions.map((action) => (
                                  <button
                                    type="button"
                                    key={`${task.task_id}-${action.id}`}
                                    onClick={() => runContractAction(action, "runtime")}
                                    disabled={operatorPending || !action.command}
                                    className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                                  >
                                    {action.label}
                                  </button>
                                ))}
                              </div>
                            ) : null}
                            {task.tool_events.length ? (
                              <div className="mt-2 flex flex-wrap gap-2">
                                {task.tool_events.map((event, index) => (
                                  <span
                                    key={`${task.task_id}-${event.name ?? "tool"}-${index}`}
                                    className="rounded-full border border-slate-300/80 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-700"
                                  >
                                    {(event.name ?? "tool")} · {(event.status ?? "unknown")}
                                  </span>
                                ))}
                              </div>
                            ) : null}
                            {task.error ? (
                              <div className="mt-2 text-[11px] text-rose-700">{task.error}</div>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-muted-foreground">
                No workers exposed.
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <AdapterActionButton binding={resolveActionBinding("open_kernel_settings")} />
            <AdapterActionButton binding={resolveActionBinding("restart_runtime")} />
            <AdapterActionButton binding={resolveActionBinding("restart_engine")} />
          </div>
        </section>

        <section className={paneClass("workspace")}>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Workspace
          </div>
          <div className="rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="truncate font-medium text-foreground">
              {activeWorkspaceScope?.project_name ?? "Default workspace"}
            </div>
            <div className="mt-1 break-all text-xs text-muted-foreground">
              {activeWorkspaceScope?.project_path ?? "No explicit project attached"}
            </div>
            <div className="mt-3 flex items-center gap-2">
              <span
                className={cn(
                  "rounded-full border px-2.5 py-1 text-[11px] font-medium",
                  chipTone(!workspaceError),
                )}
              >
                {workspaceError ? "workspace warning" : "workspace healthy"}
              </span>
              <button
                type="button"
                onClick={() => void handleTimelineRoute(firstEventRoute("workspace"))}
                disabled={!firstEventRoute("workspace")?.command}
                className="rounded-full border border-slate-300/80 bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-700 transition-colors hover:bg-slate-200"
              >
                route from shell
              </button>
            </div>
            {workspaceError ? (
              <div className="mt-3 rounded-xl border border-amber-500/20 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                {workspaceError}
              </div>
            ) : null}
          </div>
        </section>

        <section className={paneClass("faults")}>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Fault control
          </div>
          <div className="grid gap-3 xl:grid-cols-3">
            <div className="xl:col-span-3 grid gap-3 md:grid-cols-4">
              <div className="rounded-xl border border-rose-200/80 bg-rose-50/70 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-rose-700">Native fault modules</div>
                <div className="mt-2 text-lg font-semibold text-rose-950">{nativeFaultModules.length}</div>
              </div>
              <div className="rounded-xl border border-amber-200/80 bg-amber-50/70 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-amber-700">Faulted bridges</div>
                <div className="mt-2 text-lg font-semibold text-amber-950">{faultedBridges.length}</div>
              </div>
              <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-slate-600">Supervisor</div>
                <div className="mt-2 text-sm font-semibold text-slate-950">
                  {diagnostics?.supervisor ?? runtimeControl?.fault_posture.supervisor ?? "unknown"}
                </div>
              </div>
              <div className="rounded-xl border border-fuchsia-200/80 bg-fuchsia-50/70 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-fuchsia-700">Recent console errors</div>
                <div className="mt-2 text-lg font-semibold text-fuchsia-950">{recentErrors.length}</div>
              </div>
            </div>
            <div className="rounded-xl border border-rose-200/80 bg-rose-50/70 p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-rose-700">
                  Native faults
                </div>
                <ConsoleBadge label="modules" value={`${nativeFaultModules.length}`} tone="amber" />
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {nativeFaultModules.length ? nativeFaultModules.slice(0, 6).map(([name, state]) => (
                  <button
                    key={name}
                    type="button"
                    onClick={() => runContractAction(state?.actions?.find((action) => action.id === "inspect_native_module"), "modules")}
                    disabled={operatorPending || !state?.actions?.find((action) => action.id === "inspect_native_module")?.command}
                    className="rounded-full border border-rose-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-rose-700 transition-colors hover:bg-rose-100"
                  >
                    {name}:{state?.last_code ?? 0}
                  </button>
                )) : (
                  <span className="text-xs text-rose-700/80">No native module faults.</span>
                )}
              </div>
            </div>
            <div className="rounded-xl border border-amber-200/80 bg-amber-50/70 p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-amber-700">
                  Bridge faults
                </div>
                <ConsoleBadge label="bridges" value={`${faultedBridges.length}`} tone="amber" />
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {faultedBridges.length ? faultedBridges.slice(0, 6).map((bridge) => (
                  <button
                    key={bridge.adapter}
                    type="button"
                    onClick={() => runContractAction(bridge.actions?.find((action) => action.id === "inspect_bridge"), "adapters")}
                    disabled={operatorPending || !bridge.actions?.find((action) => action.id === "inspect_bridge")?.command}
                    className="rounded-full border border-amber-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-amber-700 transition-colors hover:bg-amber-100"
                  >
                    {bridge.adapter}:{bridge.runtime_stage ?? bridge.health}
                  </button>
                )) : (
                  <span className="text-xs text-amber-700/80">No bridge faults.</span>
                )}
              </div>
            </div>
            <div className="rounded-xl border border-violet-200/80 bg-violet-50/70 p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-violet-700">
                  Shell errors
                </div>
                <ConsoleBadge label="recent" value={`${recentErrors.length}`} tone="amber" />
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {recentErrors.length ? recentErrors.slice(0, 4).map((error) => (
                  <button
                    key={error.id}
                    type="button"
                    onClick={() => runContractAction(faultAction("inspect_faults"), "faults")}
                    disabled={operatorPending || !faultAction("inspect_faults")?.command}
                    className="rounded-full border border-violet-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-violet-700 transition-colors hover:bg-violet-100"
                  >
                    {error.kind}
                  </button>
                )) : (
                  <span className="text-xs text-violet-700/80">No shell errors.</span>
                )}
              </div>
            </div>
          </div>
          <div className="rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="mb-3 grid gap-2 md:grid-cols-2">
              <Row label="Supervisor" value={runtimeControl?.fault_posture.supervisor ?? diagnostics?.supervisor ?? "unknown"} />
              <Row label="Fault level" value={runtimeControl?.fault_posture.last_level ?? "clear"} />
              <Row label="Maintenance" value={runtimeControl?.maintenance_mode?.enabled ? "enabled" : "off"} />
              <Row label="Gate" value={runtimeControl?.execution_gate?.state ?? "open"} />
            </div>
            <div className="mb-3 grid gap-3 md:grid-cols-3">
              <div className="rounded-lg border border-slate-200/80 bg-white/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500">Privilege gate</div>
                <div className="mt-2 text-sm font-semibold text-slate-950">
                  {allowsPrivilegedControls ? "recovery-enabled" : "inspection-only"}
                </div>
              </div>
              <div className="rounded-lg border border-rose-200/80 bg-rose-50/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-rose-700">Escalation path</div>
                <div className="mt-2 text-sm font-semibold text-rose-950">
                  {runtimeControl?.fault_posture.supervisor ?? diagnostics?.supervisor ?? "kernel-supervisor"}
                </div>
              </div>
              <div className="rounded-lg border border-amber-200/80 bg-amber-50/80 p-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-amber-700">Recommended move</div>
                <div className="mt-2 text-sm font-semibold text-amber-950">
                  {recentErrors.length || nativeFaultModules.length || faultedBridges.length ? "inspect then clear" : "hold steady"}
                </div>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => runContractAction(faultAction("inspect_faults"), "faults")}
                disabled={operatorPending || !faultAction("inspect_faults")?.command}
                className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
              >
                inspect
              </button>
              {actionAllowed(faultAction("clear_faults")) ? (
                <>
                  <button
                    type="button"
                    onClick={() => runContractAction(faultAction("clear_faults"), "faults")}
                    disabled={operatorPending || !faultAction("clear_faults")?.command}
                    className="rounded-full border border-emerald-300/80 bg-emerald-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-emerald-700 transition-colors hover:bg-emerald-100"
                  >
                    clear
                  </button>
                  <button
                    type="button"
                    onClick={() => runContractAction(faultAction("record_fault"), "faults")}
                    disabled={operatorPending || !faultAction("record_fault")?.command}
                    className="rounded-full border border-rose-300/80 bg-rose-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-rose-700 transition-colors hover:bg-rose-100"
                  >
                    record
                  </button>
                  <button
                    type="button"
                    onClick={() => runContractAction(faultAction("enter_maintenance"), "control_plane")}
                    disabled={operatorPending || !faultAction("enter_maintenance")?.command}
                    className="rounded-full border border-amber-300/80 bg-amber-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-amber-700 transition-colors hover:bg-amber-100"
                  >
                    maintenance on
                  </button>
                  <button
                    type="button"
                    onClick={() => runContractAction(faultAction("exit_maintenance"), "control_plane")}
                    disabled={operatorPending || !faultAction("exit_maintenance")?.command}
                    className="rounded-full border border-cyan-300/80 bg-cyan-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-cyan-700 transition-colors hover:bg-cyan-100"
                  >
                    maintenance off
                  </button>
                </>
              ) : null}
            </div>
            {!allowsPrivilegedControls ? (
              <div className="mt-3 rounded-md border border-amber-200/80 bg-amber-50/80 px-3 py-2 text-[11px] text-amber-800">
                This shell can audit faults, but clear, record, and maintenance transitions stay locked until the runtime is elevated.
              </div>
            ) : null}
          </div>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Recent faults
          </div>
          <div className="rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="mb-3 flex flex-wrap gap-2">
              <AdapterActionButton binding={resolveActionBinding("record_fault")} />
              <AdapterActionButton binding={resolveActionBinding("clear_fault")} />
            </div>
            {recentErrors.length ? (
              <div className="space-y-2">
                {recentErrors.map((error) => (
                  <div
                    key={error.id}
                    className="rounded-md border border-rose-500/15 bg-rose-50 px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-rose-700">
                        {error.kind}
                      </span>
                      <span className="text-[11px] text-rose-500">
                        {new Date(error.at).toLocaleTimeString()}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-rose-900">{error.message}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-muted-foreground">
                No kernel faults captured in this shell session.
              </div>
            )}
          </div>
          <div className="rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Kernel event log
            </div>
            {eventLog.length ? (
              <div className="space-y-2">
                {eventLog.map((event) => (
                  <div
                    key={event.id}
                    className="rounded-md border border-slate-200/80 bg-slate-50/80 px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-700">
                        {event.action}
                      </span>
                      <span className="text-[11px] text-slate-500">{event.state}</span>
                    </div>
                    <div className="mt-1 text-xs text-slate-800">{event.message}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-muted-foreground">
                No kernel events recorded.
              </div>
            )}
          </div>
        </section>

        <section className={paneClass("control_plane")}>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Target posture
          </div>
          <div className="rounded-xl border border-border/70 bg-background/80 p-3 text-xs text-muted-foreground">
            <div className="font-medium text-foreground">
              {embeddedTargetHint ?? "Desktop execution kernel with room for embedded targets"}
            </div>
            {runtimeControl ? (
              <div className="mt-2 grid gap-2 rounded-md border border-slate-300/70 bg-slate-50/80 p-3">
                <Row label="Active adapter" value={runtimeControl.active_adapter ?? "unset"} />
                <Row label="Execution gate" value={runtimeControl.execution_gate?.state ?? "open"} />
                <Row
                  label="Gate reason"
                  value={runtimeControl.execution_gate?.reason ?? "operator-ready"}
                />
                <Row
                  label="Maintenance"
                  value={runtimeControl.maintenance_mode?.enabled ? "enabled" : "off"}
                />
                <Row label="Supervisor" value={runtimeControl.fault_posture.supervisor} />
                <Row label="Restart policy" value={runtimeControl.fault_posture.restart_policy} />
                <Row label="Fault level" value={runtimeControl.fault_posture.last_level} />
                <Row
                  label="Module count"
                  value={`${diagnostics?.snapshot.module_count ?? runtimeModules.length}`}
                />
                <Row
                  label="Bridge count"
                  value={`${diagnostics?.snapshot.bridge_count ?? runtimeBridges.length}`}
                />
              </div>
            ) : null}
            <div className="mt-2">
              Mira is being shaped as a reusable execution kernel, so the operator surface can eventually
              supervise constrained runtimes, firmware workflows, and board-level automation instead of
              only desktop chat sessions.
            </div>
          </div>
        </section>
      </div>
    </aside>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </span>
      <span className="truncate font-medium text-foreground">{value}</span>
    </div>
  );
}

function ConsoleBadge({
  label,
  value,
  tone = "slate",
}: {
  label: string;
  value: string;
  tone?: "slate" | "emerald" | "amber";
}) {
  const toneClass =
    tone === "emerald"
      ? "border-emerald-300/80 bg-emerald-50 text-emerald-700"
      : tone === "amber"
        ? "border-amber-300/80 bg-amber-50 text-amber-700"
        : "border-slate-300/80 bg-slate-100 text-slate-700";
  return (
    <span className={cn("rounded-md border px-2 py-1 text-[10px] uppercase tracking-[0.14em]", toneClass)}>
      {label}: <span className="font-semibold">{value}</span>
    </span>
  );
}

function AdapterActionButton({
  binding,
}: {
  binding: KernelOperatorActionBinding;
}) {
  const resolved = binding;
  return (
    <button
      type="button"
      onClick={resolved.onTrigger}
      disabled={!resolved.enabled}
      className={cn(
        "rounded-full border px-2.5 py-1 text-[11px] transition-colors",
        resolved.enabled
          ? "border-slate-300/80 bg-slate-900 text-white hover:bg-slate-800"
          : "border-slate-300/80 bg-slate-100 text-slate-500",
      )}
      title={
        resolved.availability === "planned"
          ? "Planned kernel path"
          : resolved.requiredRole === "root"
            ? resolved.privilegedReason ?? "Requires root-level privileges"
            : resolved.privileged
              ? resolved.privilegedReason ?? "Requires elevated privileges"
          : resolved.targetPane
            ? `Focus ${resolved.targetPane}`
            : undefined
      }
    >
      {resolved.label}
      {resolved.requiredRole === "root" ? " · root" : resolved.availability === "planned" ? " · planned" : ""}
    </button>
  );
}
