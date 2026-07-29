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
  chipTone,
  findActionById,
  formatBridgeCommandSummary,
  formatKernelTimestamp,
  formatKernelTimestampList,
  formatNativeCommandSummary,
  noneValue,
  operatorPanelTone,
  toolFamilyChipTone,
} from "./engineering/kernel-console-format";
import { resolveShellRegistration } from "./registry";
import type { KernelOperatorActionBinding } from "./useKernelOperatorActions";
import type { KernelConsoleErrorEntry } from "./useKernelConsoleState";

function renderNativeModuleChip({
  state,
  operatorPending,
  pane,
  className,
  label,
  onRun,
}: {
  name: string;
  state: { status?: string | null; last_code?: number | null; actions?: Array<{ id?: string | null; command?: string | null }> | null } | null | undefined;
  operatorPending: boolean;
  pane: string;
  className: string;
  label: string;
  onRun: (action: { command?: string | null } | undefined, pane: string) => void;
}) {
  const inspectNativeModuleAction = findActionById(state?.actions, "inspect_native_module");
  return (
    <button
      type="button"
      onClick={() => onRun(inspectNativeModuleAction, pane)}
      disabled={operatorPending || !inspectNativeModuleAction?.command}
      className={className}
    >
      {label}
    </button>
  );
}

function renderNativeCommandChip({
  command,
  index,
  operatorPending,
  onRun,
}: {
  command: {
    updated_at_ms?: number | null;
    target?: string | null;
    action?: string | null;
    actions?: Array<{ id?: string | null; command?: string | null }> | null;
    status?: string | null;
    queue_depth?: number | null;
  };
  index: number;
  operatorPending: boolean;
  onRun: (action: { command?: string | null } | undefined, pane: string) => void;
}) {
  const replayRecentAction = findActionById(command.actions, "replay_recent_command");
  return (
    <button
      key={`${command.updated_at_ms ?? "native"}-${command.target ?? "target"}-${command.action ?? index}`}
      type="button"
      onClick={() => onRun(replayRecentAction, "adapters")}
      disabled={operatorPending || !replayRecentAction?.command}
      className="rounded-full border border-slate-300/80 bg-slate-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-100"
    >
      {formatNativeCommandSummary(command)}
    </button>
  );
}

function renderConsoleEmptyState(message: string, className = "text-xs text-muted-foreground") {
  return <span className={className}>{message}</span>;
}

function buildNativeControlRows(input: {
  nativeLastCommand: {
    target?: string | null;
    action?: string | null;
    value?: string | null;
    artifact?: string | null;
  } | null | undefined;
  lastNativeContext: {
    command: string;
    status: string;
    code: number;
    updatedAt: number | null;
  };
  nativeSnapshot: {
    bridge_artifact?: string | null;
    command_depth?: number | null;
  } | null | undefined;
  moduleFocus: string | null | undefined;
}) {
  return [
    { label: "Last target", value: noneValue(input.nativeLastCommand?.target) },
    { label: "Last action", value: noneValue(input.nativeLastCommand?.action) },
    { label: "Last command", value: input.lastNativeContext.command },
    { label: "Last status", value: input.lastNativeContext.status },
    { label: "Last code", value: String(input.lastNativeContext.code) },
    { label: "Last value", value: noneValue(input.nativeLastCommand?.value) },
    { label: "Artifact", value: noneValue(input.nativeLastCommand?.artifact ?? input.nativeSnapshot?.bridge_artifact) },
    { label: "Module focus", value: noneValue(input.moduleFocus) },
    { label: "Command backlog", value: `${input.nativeSnapshot?.command_depth ?? 0}` },
    { label: "Updated", value: input.lastNativeContext.updatedAt ? formatKernelTimestamp(input.lastNativeContext.updatedAt) : "none" },
  ];
}

function nativeQueueDepth(snapshot: {
  queue_depth?: number | null;
  command_depth?: number | null;
} | null | undefined): number {
  return snapshot?.queue_depth ?? snapshot?.command_depth ?? 0;
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
  const hostContract = resolveShellRegistration(shellDescriptor).hostContract;
  const shellMode = hostContract.mode;
  const privilegeRole = hostContract.privilege.role;
  const canElevate = hostContract.privilege.canElevate;
  const shellAllowsPrivilegedControls = hostContract.surfaces.allowPrivilegedRuntimeControls;
  const allowsPrivilegedControls = shellAllowsPrivilegedControls && (privilegeRole === "root" || canElevate);
  const operatorReadyLabel = "operator-ready";
  const privilegePosture = {
    roleLabel: privilegeRole,
    contractLabel: shellAllowsPrivilegedControls ? "runtime control contract enabled" : "restricted shell contract",
    accessLabel: allowsPrivilegedControls ? "root-enabled" : "observe-only",
    recoveryLabel: allowsPrivilegedControls ? "recovery-enabled" : "inspection-only",
    capabilityLabel: shellAllowsPrivilegedControls
      ? (canElevate && privilegeRole !== "root" ? "elevation-capable" : operatorReadyLabel)
      : "restricted shell",
    summary: privilegeRole === "root"
      ? "root shell with live runtime control"
      : canElevate
        ? "user shell with controlled elevation"
        : "user shell in observe-first posture",
  };
  const privilegeWorkflow = {
    mode: hostContract.privilege.elevationMode ?? "none",
    elevateHint: hostContract.privilege.elevateHint ?? "none",
    dropHint: hostContract.privilege.dropHint ?? "none",
    sessionPolicy: hostContract.privilege.sessionPolicy ?? "observe-only",
  };
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
  const diagnostics = kernelManifest?.diagnostics ?? null;
  const boardSnapshot = diagnostics?.snapshot.board;
  const nativeSnapshot = diagnostics?.snapshot.native;
  const nativeLastCommand = nativeSnapshot?.last_command;
  const nativeModuleEntries = Object.entries(nativeSnapshot?.modules ?? {});
  const profile = kernelManifest?.profile ?? null;
  const adapterContract = kernelManifest?.targets.adapter ?? null;
  const runtimeAdapters = kernelManifest?.runtime_adapters.slice(0, 3) ?? [];
  const runtimeBridges = kernelManifest?.runtime_bridges.slice(0, 4) ?? [];
  const runtimeModules = kernelManifest?.runtime_modules.slice(0, 6) ?? [];
  const runtimeControl = kernelManifest?.runtime_control ?? null;
  const operatorConsole = kernelManifest?.operator_console ?? null;
  const operatorActionRegistry = operatorConsole?.action_registry ?? [];
  const runtimeCapabilities = kernelManifest?.capabilities ?? null;
  const executionContract = kernelManifest?.execution ?? null;
  const goalState = diagnostics?.snapshot.goal_state;
  const boardAttachmentLabel = boardSnapshot?.attached ? "attached" : "detached";
  const nativeHealthLabel = nativeSnapshot?.health ?? "unknown";
  const executionLanes = kernelManifest?.execution_lanes.slice(0, 4) ?? [];
  const sessionControls = kernelManifest?.session_controls?.actions ?? [];
  const sessionControlAction = (id: string) => sessionControls.find((action) => action.id === id);
  const inspectSessionAction = sessionControlAction("inspect_session");
  const inspectGoalAction = sessionControlAction("inspect_goal");
  const inspectContinuationAction = sessionControlAction("inspect_continuation");
  const resumeGoalAction = sessionControlAction("resume_goal");
  const completeGoalAction = sessionControlAction("complete_goal");
  const cancelGoalAction = sessionControlAction("cancel_goal");
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
  const selectedBridgeInspectAction = selectedBridgeAction("inspect_bridge");
  const selectedBridgeRestartAction = selectedBridgeAction("restart_bridge");
  const selectedBridgeMarkFaultAction = selectedBridgeAction("mark_bridge_fault");
  const selectedBridgeClearFaultAction = selectedBridgeAction("clear_bridge_fault");
  const dispatchInspectAction = dispatchQueueAction("inspect_dispatch");
  const dispatchPrioritizeAction = dispatchQueueAction("prioritize_dispatch");
  const dispatchDelegateGoalAction = dispatchQueueAction("delegate_goal");
  const dispatchDelegateSubagentAction = dispatchQueueAction("delegate_subagent");
  const dispatchCompleteAction = dispatchQueueAction("complete_dispatch");
  const dispatchFailAction = dispatchQueueAction("fail_dispatch");
  const dispatchDrainAction = dispatchQueueAction("drain_dispatch");
  const dispatchClearAction = dispatchQueueAction("clear_dispatch");
  const clearFaultsAction = faultAction("clear_faults");
  const inspectFaultsAction = faultAction("inspect_faults");
  const recordFaultAction = faultAction("record_fault");
  const enterMaintenanceAction = faultAction("enter_maintenance");
  const exitMaintenanceAction = faultAction("exit_maintenance");
  const inspectRuntimeAction = runtimeTopologyAction("inspect_runtime");
  const runtimeOrchestrationAction = runtimeTopologyAction("runtime_orchestration");
  const embeddedBoardStatusAction = embeddedTopologyAction("board_status");
  const embeddedInspectAction = embeddedTopologyAction("inspect_embedded");
  const embeddedRefreshPortsAction = embeddedTopologyAction("refresh_board_ports");
  const nativeReplayLastAction = nativeAction("replay_last");
  const nativeStatusAction = nativeAction("native_status");
  const nativeLastCommandAction = nativeAction("native_last_command");
  const nativeModulesAction = nativeAction("native_modules");
  const nativeFocusLastTargetAction = nativeAction("focus_last_target");
  const nativeOpenLastTargetAction = nativeAction("open_last_target");
  const nativeStatusCommand = "native status";
  const nativeReplayLastCommand = "native replay-last";
  const nativeLastCommandQuery = "native last-command";
  const selectedModuleInspectNativeStatusAction = selectedModuleAction("inspect_native_status");
  const selectedModuleFocusNativeAction = selectedModuleAction("focus_native");
  const selectedModuleInspectNativeAction = selectedModuleAction("inspect_native");
  const selectedModuleShowModuleAction = selectedModuleAction("show_module");
  const selectedModuleFillNativeInspectAction = selectedModuleAction("fill_native_inspect");
  const selectedModuleFillNativeReplayAction = selectedModuleAction("fill_native_replay");
  const findModuleAction = (moduleName: string, actionId: string) =>
    runtimeModules.find((module) => module.name === moduleName)?.actions?.find((action) => action.id === actionId)
    ?? runtimeTopologyModules.find((module) => module.name === moduleName)?.actions?.find((action) => action.id === actionId)
    ?? null;
  const moduleShowCommand = (moduleName: string) => findModuleAction(moduleName, "show_module")?.command ?? null;
  const moduleFocusCommand = (moduleName: string) => findModuleAction(moduleName, "focus_native")?.command ?? null;
  const moduleInspectFillCommand = (moduleName: string) =>
    findModuleAction(moduleName, "fill_native_inspect")?.command ?? null;
  const primaryEventAction = (event?: { actions?: Array<{ pane?: string | null; command?: string | null }> | null } | null) =>
    event?.actions?.find((action) => !!action.command) ?? null;
  const executionTimeline = eventLog.slice(0, 6).map((event, index) => ({
    id: String(event.id ?? index + 1),
    type: String(event.type ?? "event"),
    state: String(event.state ?? "unknown"),
    message: String(event.message ?? "no message"),
    route: primaryEventAction(event),
  }));
  const firstEventRoute = (pane: string) =>
    executionTimeline.find((event) => event.route?.pane === pane)?.route ?? null;
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
      if (result && typeof result === "object") appendOperatorResult(result);
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
      if (result && typeof result === "object") appendOperatorResult(result);
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
        if (result && typeof result === "object") appendOperatorResult(result);
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
  const operatorPlaybooks = useMemo(() => {
    const recoveryCommands = [
      {
        label: inspectFaultsAction?.command ?? "fault show",
        command: inspectFaultsAction?.command ?? "fault show",
        locked: false,
      },
      {
        label: clearFaultsAction?.command ?? "fault clear",
        command: clearFaultsAction?.command ?? "fault clear",
        locked: !actionAllowed(clearFaultsAction),
      },
      {
        label: dispatchDrainAction?.command ?? "tool drain",
        command: dispatchDrainAction?.command ?? "tool drain",
        locked: !actionAllowed(dispatchDrainAction),
      },
      {
        label: "runtime health",
        command: "runtime health",
        locked: false,
      },
    ];
    const embeddedCommands = [
      {
        label: embeddedBoardStatusAction?.command ?? "board status",
        command: embeddedBoardStatusAction?.command ?? "board status",
        locked: false,
      },
      {
        label: embeddedRefreshPortsAction?.command ?? "board ports",
        command: embeddedRefreshPortsAction?.command ?? "board ports",
        locked: false,
      },
      {
        label: "board mode",
        command: "board mode",
        locked: false,
      },
      {
        label: "board transport",
        command: "board transport",
        locked: false,
      },
      {
        label: embeddedInspectAction?.command ?? "topology embedded",
        command: embeddedInspectAction?.command ?? "topology embedded",
        locked: false,
      },
    ];
    const moduleCommand = {
      label: selectedModuleInspectNativeAction?.command
        ?? selectedModuleFillNativeInspectAction?.command
        ?? "native inspect memory",
      command: selectedModuleInspectNativeAction?.command
        ?? selectedModuleFillNativeInspectAction?.command
        ?? "native inspect memory",
      locked: false,
    };
    return [
      {
        label: "operator bring-up",
        tone: "border-cyan-700 bg-cyan-950 text-cyan-100",
        detail: "runtime / scheduler / workspace",
        commands: [
          { label: "runtime health", command: "runtime health", locked: false },
          { label: "scheduler status", command: "scheduler status", locked: false },
          { label: "workspace status", command: "workspace status", locked: false },
          { label: "repo tools", command: "repo tools", locked: false },
        ],
      },
      {
        label: "fault recovery",
        tone: "border-rose-700 bg-rose-950 text-rose-100",
        detail: privilegeRole === "root" || canElevate ? "fault lane / drain / recover" : "observe-first recovery path",
        commands: recoveryCommands.filter((item) => Boolean(item.command)),
      },
      {
        label: "embedded attach",
        tone: "border-amber-700 bg-amber-950 text-amber-100",
        detail: "board / ports / native module",
        commands: [...embeddedCommands.filter((item) => Boolean(item.command)), moduleCommand].filter((item) => Boolean(item.command)),
      },
    ];
  }, [
    actionAllowed,
    canElevate,
    clearFaultsAction,
    dispatchDrainAction,
    embeddedBoardStatusAction,
    embeddedInspectAction,
    embeddedRefreshPortsAction,
    inspectFaultsAction,
    privilegeRole,
    selectedModuleFillNativeInspectAction,
    selectedModuleInspectNativeAction,
  ]);
  const nativeReplayCommands = useMemo(() => {
    const commands = ["native status", "native last-command", "native replay-last", "native inspect memory", "native focus memory", "native modules"];
    const openLastTargetCommand = nativeAction("open_last_target")?.command;
    if (openLastTargetCommand) {
      commands.push(openLastTargetCommand);
    }
    if (selectedModuleFocusNativeAction?.command) {
      commands.push(selectedModuleFocusNativeAction.command);
    }
    if (selectedModuleInspectNativeAction?.command) {
      commands.push(selectedModuleInspectNativeAction.command);
    }
    if (selectedModuleFillNativeReplayAction?.command) {
      commands.push(selectedModuleFillNativeReplayAction.command);
    }
    return commands;
  }, [nativeAction, selectedModuleFillNativeReplayAction, selectedModuleFocusNativeAction, selectedModuleInspectNativeAction]);
  const paneClass = (pane: string) =>
    selectedPane === pane ? "space-y-2" : "hidden";
  const lastNativeContext = {
    status: nativeLastCommand?.status ?? "idle",
    code: nativeLastCommand?.code ?? 0,
    command: nativeLastCommand?.command ?? nativeLastCommand?.action ?? "none",
    updatedAt: nativeLastCommand?.updated_at_ms ?? null,
  };
  const nativeFaultModules = nativeModuleEntries.filter(([, state]) => state?.status === "fault");
  const faultedBridges = runtimeBridges.filter((bridge) => bridge.health === "fault");
  const eventLaneCounts = executionTimeline.reduce(
    (counts, event) => {
      if (event.type.includes("fault") || event.type.includes("maintenance")) {
        counts.fault += 1;
      }
      if (event.type.includes("turn") || event.type.includes("execution") || event.type.includes("session")) {
        counts.runtime += 1;
      }
      if (event.type.includes("bridge") || event.type.includes("adapter") || event.type.includes("board")) {
        counts.bridge += 1;
      }
      return counts;
    },
    { fault: 0, runtime: 0, bridge: 0 },
  );
  const maturitySummary = [
    runtimeCapabilities?.threads ? "threads" : null,
    runtimeCapabilities?.api ? "api" : null,
    runtimeCapabilities?.gui ? "gui" : null,
    runtimeCapabilities?.approvals ? "approvals" : null,
  ].filter(Boolean).join(" · ") || "minimal kernel";
  const faultSummary = nativeFaultModules.length || faultedBridges.length || eventLaneCounts.fault
    ? `${nativeFaultModules.length} native / ${faultedBridges.length} bridge / ${eventLaneCounts.fault} events`
    : "no active kernel faults";
  const dispatchRestrictionHint = dispatchPrioritizeAction
    ? actionRestrictionReason(dispatchPrioritizeAction)
    : null;
  const bridgeRestrictionHint = selectedBridgeRestartAction
    ? actionRestrictionReason(selectedBridgeRestartAction)
    : null;
  const clearFaultRestrictionHint = clearFaultsAction
    ? actionRestrictionReason(clearFaultsAction)
    : null;
  const dispatchActionButtons = [
    {
      action: dispatchPrioritizeAction,
      pane: "runtime",
      label: "prioritize",
      className: "rounded-full border border-amber-300/80 bg-amber-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-amber-700 transition-colors hover:bg-amber-100",
    },
    {
      action: dispatchDelegateGoalAction,
      pane: "runtime",
      label: "goal lane",
      className: "rounded-full border border-cyan-300/80 bg-cyan-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-cyan-700 transition-colors hover:bg-cyan-100",
    },
    {
      action: dispatchDelegateSubagentAction,
      pane: "runtime",
      label: "subagent",
      className: "rounded-full border border-violet-300/80 bg-violet-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-violet-700 transition-colors hover:bg-violet-100",
    },
    {
      action: dispatchCompleteAction,
      pane: "runtime",
      label: "complete",
      className: "rounded-full border border-emerald-300/80 bg-emerald-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-emerald-700 transition-colors hover:bg-emerald-100",
    },
    {
      action: dispatchFailAction,
      pane: "faults",
      label: "fail",
      className: "rounded-full border border-rose-300/80 bg-rose-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-rose-700 transition-colors hover:bg-rose-100",
    },
    {
      action: dispatchDrainAction,
      pane: "runtime",
      label: "drain",
      className: "rounded-full border border-slate-300/80 bg-slate-100 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-200",
    },
    {
      action: dispatchClearAction,
      pane: "runtime",
      label: "clear",
      className: "rounded-full border border-slate-300/80 bg-slate-100 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-200",
    },
  ] as const;
  const faultActionButtons = [
    {
      action: clearFaultsAction,
      pane: "faults",
      label: "clear",
      className: "rounded-full border border-emerald-300/80 bg-emerald-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-emerald-700 transition-colors hover:bg-emerald-100",
    },
    {
      action: recordFaultAction,
      pane: "faults",
      label: "record",
      className: "rounded-full border border-rose-300/80 bg-rose-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-rose-700 transition-colors hover:bg-rose-100",
    },
    {
      action: enterMaintenanceAction,
      pane: "control_plane",
      label: "maintenance on",
      className: "rounded-full border border-amber-300/80 bg-amber-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-amber-700 transition-colors hover:bg-amber-100",
    },
    {
      action: exitMaintenanceAction,
      pane: "control_plane",
      label: "maintenance off",
      className: "rounded-full border border-cyan-300/80 bg-cyan-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-cyan-700 transition-colors hover:bg-cyan-100",
    },
  ] as const;
  const bridgeActionButtons = [
    {
      action: selectedBridgeRestartAction,
      pane: "adapters",
      label: "restart",
      className: "rounded-full border border-cyan-300/80 bg-cyan-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-cyan-700 transition-colors hover:bg-cyan-100",
    },
    {
      action: selectedBridgeMarkFaultAction,
      pane: "faults",
      label: "mark fault",
      className: "rounded-full border border-rose-300/80 bg-rose-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-rose-700 transition-colors hover:bg-rose-100",
    },
    {
      action: selectedBridgeClearFaultAction,
      pane: "faults",
      label: "clear fault",
      className: "rounded-full border border-emerald-300/80 bg-emerald-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-emerald-700 transition-colors hover:bg-emerald-100",
    },
  ] as const;
  const nativeActionButtons = [
    {
      action: nativeStatusAction,
      pane: "adapters",
      label: "inspect native",
      className: "rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50",
    },
    {
      action: nativeLastCommandAction,
      pane: "adapters",
      label: "last command",
      className: "rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50",
    },
    {
      action: nativeModulesAction,
      pane: "modules",
      label: "native modules",
      className: "rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50",
    },
  ] as const;
  const nativeLastTargetActionButtons = [
    {
      action: nativeFocusLastTargetAction,
      pane: "modules",
      label: "focus last target",
      className: "rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100",
    },
    {
      action: nativeReplayLastAction,
      pane: "adapters",
      label: "replay last",
      className: "rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100",
    },
    {
      action: nativeOpenLastTargetAction,
      pane: "modules",
      label: "open target",
      className: "rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100",
    },
  ] as const;
  const selectedNativeModuleActionButtons = [
    {
      action: selectedModuleFocusNativeAction,
      pane: "modules",
      label: "focus selected",
      className: "rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100",
    },
    {
      action: selectedModuleInspectNativeAction,
      pane: "modules",
      label: "inspect selected",
      className: "rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100",
    },
  ] as const;
  const faultLaneRoute = firstEventRoute("faults");
  const runtimeLaneRoute = firstEventRoute("runtime");
  const adapterLaneRoute = firstEventRoute("adapters");
  const controlPlaneRows = [
    { label: "Profile", value: profile?.name ?? "unknown" },
    { label: "Shell", value: shellDescriptor?.display_name ?? "Mira" },
    { label: "Mode", value: shellMode },
    { label: "Status", value: connectionStatus },
    { label: "Model", value: runtimeModel ?? "unresolved" },
    { label: "Running", value: `${runningExecutionCount}` },
    { label: "Gate", value: runtimeControl?.execution_gate?.state ?? "open" },
    { label: "Maintenance", value: runtimeControl?.maintenance_mode?.enabled ? "enabled" : "off" },
    { label: "Gate reason", value: runtimeControl?.execution_gate?.reason ?? operatorReadyLabel },
    { label: "Supervisor", value: diagnostics?.supervisor ?? runtimeControl?.fault_posture.supervisor ?? "unknown" },
  ];
  const kernelIdentityRows = [
    { label: "App", value: kernelManifest?.identity?.app_name ?? "Mira" },
    { label: "CLI", value: kernelManifest?.identity?.cli_name ?? "mira" },
    { label: "Profile", value: profile?.name ?? "unknown" },
    { label: "Privilege", value: privilegePosture.roleLabel },
    { label: "Privileged shell", value: shellAllowsPrivilegedControls ? "enabled" : "restricted" },
    { label: "Elevation", value: canElevate ? "allowed" : "fixed" },
    { label: "GUI", value: runtimeCapabilities?.gui ? "enabled" : "off" },
    { label: "API", value: runtimeCapabilities?.api ? "enabled" : "off" },
    { label: "Threads", value: runtimeCapabilities?.threads ? "enabled" : "off" },
    { label: "Approvals", value: runtimeCapabilities?.approvals ? "enabled" : "off" },
    {
      label: "Contracts",
      value: `m${kernelManifest?.contracts?.manifest_version ?? 0}/e${kernelManifest?.contracts?.event_version ?? 0}/s${kernelManifest?.contracts?.snapshot_version ?? 0}`,
    },
  ];
  const runtimeSummaryRows = [
    { label: "Streaming", value: executionContract?.supports_streaming ? "enabled" : "off" },
    { label: "Background", value: executionContract?.supports_background ? "enabled" : "off" },
    { label: "Engine restart", value: runtimeCapabilities?.can_restart_engine ? "available" : "n/a" },
    { label: "Open logs", value: runtimeCapabilities?.can_open_logs ? "available" : "n/a" },
    { label: "Diag modules", value: `${diagnostics?.snapshot.module_count ?? runtimeModules.length}` },
    { label: "Diag bridges", value: `${diagnostics?.snapshot.bridge_count ?? runtimeBridges.length}` },
    { label: "Diag gate", value: diagnostics?.snapshot.execution_gate ?? runtimeControl?.execution_gate?.state ?? "open" },
    { label: "Diag phase", value: diagPhase ?? "idle" },
    { label: "Diag iter", value: `${diagIteration ?? 0}` },
    { label: "Tool wait", value: `${diagPendingToolCalls}` },
    { label: "Subagents", value: `${diagSubagentWorkers}` },
    { label: "Board", value: boardAttachmentLabel },
    { label: "Board mode", value: boardSnapshot?.runtime_mode ?? "unprobed" },
    { label: "Board health", value: boardSnapshot?.health ?? "unknown" },
    { label: "Native health", value: nativeHealthLabel },
    { label: "Native queue", value: `${nativeSnapshot?.queue_depth ?? nativeSnapshot?.command_depth ?? 0}` },
    { label: "Native modules", value: `${nativeSnapshot?.module_count ?? nativeModuleEntries.length}` },
    { label: "Native bridge", value: nativeSnapshot?.bridge_artifact ?? "none" },
  ];
  const faultSummaryRows = [
    { label: "Supervisor", value: runtimeControl?.fault_posture.supervisor ?? diagnostics?.supervisor ?? "unknown" },
    { label: "Fault level", value: runtimeControl?.fault_posture.last_level ?? "clear" },
    { label: "Maintenance", value: runtimeControl?.maintenance_mode?.enabled ? "enabled" : "off" },
    { label: "Gate", value: runtimeControl?.execution_gate?.state ?? "open" },
  ];
  const cockpitOverviewCards = [
    {
      label: "Execution fabric",
      value: `${runningExecutionCount} active`,
      detail: `${executionLanes.length} lanes · ${diagPendingToolCalls} tool waits`,
      tone: "border-cyan-200/80 bg-cyan-50/70",
    },
    {
      label: "Kernel graph",
      value: `${runtimeModules.length} modules`,
      detail: `${runtimeBridges.length} bridges · ${runtimeAdapters.length} adapters`,
      tone: "border-emerald-200/80 bg-emerald-50/70",
    },
    {
      label: "Fault domain",
      value: nativeFaultModules.length || faultedBridges.length || eventLaneCounts.fault ? "attention" : "clear",
      detail: `${nativeFaultModules.length} modules · ${faultedBridges.length} bridges · ${eventLaneCounts.fault} lane`,
      tone: "border-rose-200/80 bg-rose-50/70",
    },
    {
      label: "Embedded target",
      value: embeddedTargetHint ?? boardSnapshot?.target ?? "not attached",
      detail: `${boardAttachmentLabel} · ${boardSnapshot?.transport ?? "transport unknown"}`,
      tone: "border-amber-200/80 bg-amber-50/70",
    },
  ] as const;
  const cockpitQuickRoutes = [
    {
      label: "Inspect runtime",
      pane: "runtime",
      command: inspectRuntimeAction?.command ?? "runtime health",
      tone: "border-cyan-300/80 bg-cyan-50 text-cyan-700 hover:bg-cyan-100",
    },
    {
      label: "Focus faults",
      pane: "faults",
      command: inspectFaultsAction?.command ?? faultLaneRoute?.command ?? "fault inspect",
      tone: "border-rose-300/80 bg-rose-50 text-rose-700 hover:bg-rose-100",
    },
    {
      label: "Open module graph",
      pane: "modules",
      command: selectedModuleShowModuleAction?.command ?? moduleShowCommand(selectedModuleName ?? "") ?? "module list",
      tone: "border-emerald-300/80 bg-emerald-50 text-emerald-700 hover:bg-emerald-100",
    },
    ...(nativeFaultModules[0]?.[0]
      ? [{
          label: "Focus fault module",
          pane: "modules",
          command: moduleShowCommand(nativeFaultModules[0][0]) ?? moduleFocusCommand(nativeFaultModules[0][0]) ?? "module list",
          tone: "border-rose-300/80 bg-rose-50 text-rose-700 hover:bg-rose-100",
        }]
      : []),
    {
      label: "Board status",
      pane: "adapters",
      command: embeddedBoardStatusAction?.command ?? "board status",
      tone: "border-amber-300/80 bg-amber-50 text-amber-700 hover:bg-amber-100",
    },
  ].filter((item) => item.command);
  const cockpitPrimitiveSurface = [
    {
      label: "Tool contracts",
      value: `${operatorActionRegistry.length}`,
      detail: "console actions exposed to the shell",
      tone: "border-cyan-200/80 bg-cyan-50/70",
    },
    {
      label: "Execution lanes",
      value: `${executionLanes.length}`,
      detail: executionLanes.map((lane) => lane.id).slice(0, 2).join(" · ") || "none",
      tone: "border-emerald-200/80 bg-emerald-50/70",
    },
    {
      label: "Scheduler queues",
      value: `${schedulerQueues.length}`,
      detail: schedulerQueues.map((queue) => queue.id).slice(0, 2).join(" · ") || "none",
      tone: "border-slate-200/80 bg-slate-50/70",
    },
    {
      label: "Worker lanes",
      value: `${workers.length}`,
      detail: workers.map((worker) => worker.lane).slice(0, 2).join(" · ") || "none",
      tone: "border-amber-200/80 bg-amber-50/70",
    },
  ] as const;
  const toolFamilySurface = [
    {
      family: "filesystem",
      examples: "tool inspect filesystem · repo prepare-tool filesystem",
    },
    {
      family: "shell",
      examples: "tool inspect shell · tool dispatch shell",
    },
    {
      family: "web",
      examples: "tool inspect search · tool dispatch search",
    },
    {
      family: "subagent / long-task",
      examples: "tool delegate-subagent · tool delegate-goal",
    },
    {
      family: "mcp / core",
      examples: "repo tools · tool status",
    },
  ] as const;
  const errorTriageRoutes = useMemo(() => recentErrors.slice(0, 4).map((error) => {
    if (error.kind === "workspace_scope_rejected") {
      return {
        id: error.id,
        label: "scope rejection",
        detail: error.message,
        pane: "workspace",
        command: activeWorkspaceScope ? "workspace scope" : "workspace status",
        tone: "border-amber-200/80 bg-amber-50/70 text-amber-900",
      };
    }
    return {
      id: error.id,
      label: "transport fault",
      detail: error.message,
      pane: "control_plane",
      command: "event tail 8",
      tone: "border-rose-200/80 bg-rose-50/70 text-rose-900",
    };
  }), [activeWorkspaceScope, recentErrors]);
  const shellErrorTriageById = useMemo(
    () => Object.fromEntries(errorTriageRoutes.map((route) => [route.id, route])),
    [errorTriageRoutes],
  );
  const faultFocusModule = useMemo(() => {
    const firstFault = nativeFaultModules[0]?.[0] ?? null;
    if (!firstFault) return null;
    return {
      name: firstFault,
      focus: moduleFocusCommand(firstFault),
      inspect: moduleInspectFillCommand(firstFault),
      show: moduleShowCommand(firstFault),
    };
  }, [moduleFocusCommand, moduleInspectFillCommand, moduleShowCommand, nativeFaultModules]);

  return (
    <aside className="hidden w-[332px] shrink-0 border-l border-border/70 bg-[linear-gradient(180deg,rgba(248,250,252,0.98)_0%,rgba(241,245,249,0.96)_100%)] lg:flex lg:flex-col xl:w-[356px]">
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
        <section className="space-y-3">
          <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-3 shadow-[0_18px_50px_rgba(15,23,42,0.08)]">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                  Kernel cockpit
                </div>
                <div className="mt-1 text-base font-semibold text-foreground">
                  Universal execution frontplane
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  One surface for runtime command, module routing, fault recovery, and embedded attachment.
                </div>
              </div>
              <div className="rounded-full border border-slate-300/80 bg-slate-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-700">
                {privilegePosture.summary}
              </div>
            </div>
            <div className="mt-3 grid gap-2 xl:grid-cols-2">
              {cockpitOverviewCards.map((card) => (
                <div key={card.label} className={cn("rounded-xl border p-3", card.tone)}>
                  <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                    {card.label}
                  </div>
                  <div className="mt-1.5 text-sm font-semibold text-slate-900">
                    {card.value}
                  </div>
                  <div className="mt-1 text-xs text-slate-600">
                    {card.detail}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {cockpitQuickRoutes.map((item) => (
                <button
                  key={item.label}
                  type="button"
                  onClick={() => {
                    onSelectPane(item.pane);
                    setOperatorCommand(item.command);
                  }}
                  disabled={operatorPending}
                  className={cn(
                    "rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] transition-colors",
                    item.tone,
                    operatorPending ? "opacity-60" : "",
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="mt-3 grid gap-2 xl:grid-cols-2">
              {cockpitPrimitiveSurface.map((item) => (
                <div key={item.label} className={cn("rounded-xl border p-3", item.tone)}>
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                      {item.label}
                    </div>
                    <div className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-700">
                      {item.value}
                    </div>
                  </div>
                  <div className="mt-1 text-xs text-slate-600">
                    {item.detail}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

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
                  General execution layer with runtime supervision, privilege-aware control, native bridge
                  control, module focus, board operations, and fault recovery in one shell.
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <ConsoleBadge label="shell" value={shellMode} tone="slate" />
                <ConsoleBadge label="role" value={privilegePosture.roleLabel} tone={privilegeRole === "root" ? "emerald" : "amber"} />
                <ConsoleBadge label="access" value={privilegePosture.accessLabel} tone={allowsPrivilegedControls ? "emerald" : "amber"} />
                <ConsoleBadge label="recovery" value={privilegePosture.recoveryLabel} tone={allowsPrivilegedControls ? "emerald" : "amber"} />
                <ConsoleBadge label="maintenance" value={runtimeControl?.maintenance_mode?.enabled ? "enabled" : "off"} tone={runtimeControl?.maintenance_mode?.enabled ? "amber" : "slate"} />
                <ConsoleBadge label="gate" value={runtimeControl?.execution_gate?.state ?? "open"} tone={runtimeControl?.execution_gate?.state === "open" ? "emerald" : "amber"} />
                <ConsoleBadge label="board" value={boardAttachmentLabel} tone={boardSnapshot?.attached ? "emerald" : "amber"} />
                <ConsoleBadge label="native" value={nativeHealthLabel} tone={nativeSnapshot?.health === "ready" ? "emerald" : "amber"} />
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
                    {privilegePosture.roleLabel}
                  </span>
                  <span className="text-xs text-slate-300">
                    {privilegePosture.capabilityLabel}
                  </span>
                </div>
                <div className="mt-2 text-xs text-slate-300">
                  {privilegePosture.summary}
                </div>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/5 p-3">
                <div className="text-[10px] uppercase tracking-[0.16em] text-slate-400">Runtime</div>
                <div className="mt-2 text-lg font-semibold text-white">{runtimeModel ?? "unresolved"}</div>
                <div className="text-xs text-slate-300">
                  {runtimeControl?.execution_gate?.reason ?? operatorReadyLabel}
                </div>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/5 p-3">
                <div className="text-[10px] uppercase tracking-[0.16em] text-slate-400">Kernel maturity</div>
                <div className="mt-2 text-lg font-semibold text-white">
                  {profile?.name ?? "unknown"}
                </div>
                <div className="text-xs text-slate-300">
                  {maturitySummary}
                </div>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/5 p-3">
                <div className="text-[10px] uppercase tracking-[0.16em] text-slate-400">Fault posture</div>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <div className="text-lg font-semibold text-white">
                    {nativeFaultModules.length || faultedBridges.length || eventLaneCounts.fault ? "attention" : "stable"}
                  </div>
                  <ConsoleBadge
                    label="recovery"
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
                <div className="text-xs text-slate-300">
                  {faultSummary}
                </div>
                <div className="mt-1 text-xs text-slate-400">
                  {runtimeControl?.maintenance_mode?.enabled ? "maintenance gate is active" : "maintenance gate is clear"}
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-[10px] uppercase tracking-[0.14em] text-slate-300">
                  <span className={cn(
                    "rounded-full border px-2 py-1",
                    nativeFaultModules.length > 0
                      ? "border-amber-300/50 bg-amber-500/10 text-amber-100"
                      : "border-white/10 bg-white/5",
                  )}>
                    modules {nativeFaultModules.length}
                  </span>
                  <span className={cn(
                    "rounded-full border px-2 py-1",
                    faultedBridges.length > 0
                      ? "border-amber-300/50 bg-amber-500/10 text-amber-100"
                      : "border-white/10 bg-white/5",
                  )}>
                    bridges {faultedBridges.length}
                  </span>
                  <span className={cn(
                    "rounded-full border px-2 py-1",
                    eventLaneCounts.fault > 0
                      ? "border-amber-300/50 bg-amber-500/10 text-amber-100"
                      : "border-white/10 bg-white/5",
                  )}>
                    lane {eventLaneCounts.fault}
                  </span>
                </div>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/5 p-3">
                <div className="text-[10px] uppercase tracking-[0.16em] text-slate-400">Mission control</div>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <div className="text-lg font-semibold text-white">
                    {goalState?.active ? "active" : "idle"}
                  </div>
                  <ConsoleBadge
                    label="lane"
                    value={diagnostics?.snapshot.dispatch_handoff_lane ?? "none"}
                    tone={goalState?.active ? "amber" : "slate"}
                  />
                </div>
                <div className="text-xs text-slate-300">
                  {goalState?.ui_summary ?? goalState?.objective ?? "no sustained objective recorded"}
                </div>
                <div className="mt-1 text-xs text-slate-400">
                  {goalState?.active
                    ? `continuations ${goalState?.continuation_rounds ?? 0} · progress ${goalState?.last_progress_at ?? "pending"}`
                    : "goal runtime is cold"}
                </div>
              </div>
            </div>
          </div>
          <div className="grid gap-2 rounded-xl border border-border/70 bg-background/80 p-3">
            <ConsoleRowGrid items={controlPlaneRows} className="grid gap-2" />
            <div className="mt-3 flex flex-wrap gap-2">
              <AdapterActionButton binding={resolveActionBinding("enter_maintenance")} />
              <AdapterActionButton binding={resolveActionBinding("exit_maintenance")} />
            </div>
          </div>
          <div className="grid gap-2 rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Kernel identity
            </div>
            <ConsoleRowGrid items={kernelIdentityRows} className="grid gap-2" />
            <div className="mt-2 flex flex-wrap gap-2">
              {kernelManifest?.targets.runtime?.length ? kernelManifest.targets.runtime.slice(0, 4).map((target) => (
                <span
                  key={target}
                  className="rounded-full border border-slate-300/80 bg-slate-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700"
                >
                  {target}
                </span>
              )) : null}
              {kernelManifest?.targets.languages?.length ? kernelManifest.targets.languages.slice(0, 4).map((language) => (
                <span
                  key={language}
                  className="rounded-full border border-cyan-300/80 bg-cyan-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-cyan-700"
                >
                  {language}
                </span>
              )) : selectedBridgeRestartAction ? (
                <span className="text-xs text-muted-foreground">
                  {bridgeRestrictionHint}
                </span>
              ) : clearFaultsAction ? (
                <span className="text-xs text-muted-foreground">
                  {clearFaultRestrictionHint}
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
              <ConsoleInfoCard
                label="Command path"
                value={selectedPane}
                detail={operatorPending ? "foreground execution active" : "operator shell ready"}
                className="rounded-lg border border-slate-800 bg-slate-950/95 px-3 py-2"
                labelClassName="text-[10px] uppercase tracking-[0.14em] text-slate-500"
                valueClassName="mt-2 text-sm font-semibold text-slate-50"
                detailClassName="text-xs text-slate-400"
              />
              <ConsoleInfoCard
                label="Privilege posture"
                value={privilegePosture.roleLabel}
                detail={privilegePosture.contractLabel}
                className="rounded-lg border border-slate-800 bg-slate-950/95 px-3 py-2"
                labelClassName="text-[10px] uppercase tracking-[0.14em] text-slate-500"
                valueClassName="mt-2 text-sm font-semibold text-slate-50"
                detailClassName="text-xs text-slate-400"
              />
              <ConsoleInfoCard
                label="Native replay"
                value={`${nativeLastCommand?.target ?? "none"}:${nativeLastCommand?.action ?? "idle"}`}
                detail={`queue ${nativeSnapshot?.queue_depth ?? nativeSnapshot?.command_depth ?? 0} · health ${nativeHealthLabel}`}
                className="rounded-lg border border-slate-800 bg-slate-950/95 px-3 py-2"
                labelClassName="text-[10px] uppercase tracking-[0.14em] text-slate-500"
                valueClassName="mt-2 text-sm font-semibold text-slate-50"
                detailClassName="text-xs text-slate-400"
              />
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
                        const command = selectedModuleInspectNativeAction?.command;
                        if (!command) return;
                        setOperatorCommand(command);
                      }}
                      disabled={operatorPending || !selectedModuleInspectNativeAction?.command}
                      className="rounded-full border border-fuchsia-700/60 bg-fuchsia-950 px-2 py-0.5 uppercase tracking-[0.12em] text-fuchsia-100 transition-colors hover:bg-fuchsia-900"
                    >
                      native inspect {selectedModule.name}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        const command = selectedModuleFillNativeReplayAction?.command;
                        if (!command) return;
                        setOperatorCommand(command);
                      }}
                      disabled={operatorPending || !selectedModuleFillNativeReplayAction?.command}
                      className="rounded-full border border-fuchsia-700/60 bg-fuchsia-950 px-2 py-0.5 uppercase tracking-[0.12em] text-fuchsia-100 transition-colors hover:bg-fuchsia-900"
                    >
                      native replay {selectedModule.name} inspect status
                    </button>
                  </>
                ) : dispatchPrioritizeAction ? (
                  <span className="text-xs text-muted-foreground">
                    {dispatchRestrictionHint}
                  </span>
                ) : null}
              </div>
              <div className="mt-3 space-y-2">
                {errorTriageRoutes.length ? (
                  <div className="space-y-2">
                    <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500">
                      recent incidents
                    </div>
                    <div className="grid gap-2 md:grid-cols-2">
                      {errorTriageRoutes.map((route) => (
                        <div key={route.id} className={cn("rounded-md border px-2 py-2", route.tone)}>
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <div className="text-[10px] uppercase tracking-[0.12em]">
                                {route.label}
                              </div>
                              <div className="mt-1 text-[10px] opacity-80">
                                {route.detail}
                              </div>
                            </div>
                            <button
                              type="button"
                              onClick={() => runTopologyCommand(route.pane, route.command)}
                              disabled={operatorPending}
                              className="rounded-full border border-current/30 bg-white/80 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] transition-colors hover:bg-white"
                            >
                              triage
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className="grid gap-2 md:grid-cols-3">
                  {operatorPlaybooks.map((playbook) => (
                    <div
                      key={playbook.label}
                      className="rounded-md border border-slate-800 bg-slate-900/80 p-2"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="text-[10px] uppercase tracking-[0.14em] text-slate-400">
                            {playbook.label}
                          </div>
                          <div className="mt-1 text-[10px] text-slate-500">
                            {playbook.detail}
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            const firstRunnable = playbook.commands.find((item) => !item.locked)?.command ?? "runtime health";
                            runQuickCommand(firstRunnable);
                          }}
                          disabled={operatorPending || !playbook.commands.some((item) => !item.locked)}
                          className={cn(
                            "rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] transition-colors",
                            playbook.tone,
                            operatorPending ? "opacity-60" : "",
                          )}
                        >
                          start
                        </button>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {playbook.commands.map((item) => (
                          <button
                            key={`${playbook.label}-${item.command}`}
                            type="button"
                            onClick={() => runQuickCommand(item.command)}
                            disabled={operatorPending || item.locked}
                            className={cn(
                              "rounded-full border border-slate-700 bg-slate-950 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-200 transition-colors hover:bg-slate-900",
                              operatorPending || item.locked ? "opacity-60" : "",
                            )}
                          >
                            {item.label}
                          </button>
                        ))}
                      </div>
                      {playbook.commands.some((item) => item.locked) ? (
                        <div className="mt-2 text-[10px] uppercase tracking-[0.12em] text-amber-400">
                          locked by privilege posture
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
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
                <div className="space-y-1">
                  <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500">
                    tool families
                  </div>
                  <div className="grid gap-2 md:grid-cols-2">
                    {toolFamilySurface.map((item) => (
                      <div
                        key={item.family}
                        className="rounded-md border border-slate-800 bg-slate-900/70 px-2 py-1.5"
                      >
                        <div className="text-[10px] uppercase tracking-[0.12em] text-slate-400">
                          {item.family}
                        </div>
                        <div className="mt-1 text-[10px] text-slate-300">
                          {item.examples}
                        </div>
                      </div>
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
                        {"family" in entry.details ? (
                          <ConsoleBadge
                            label="family"
                            value={String(entry.details.family)}
                            tone="amber"
                          />
                        ) : null}
                      </div>
                      {"family_counts" in entry.details ? (
                        <div className="mt-2 rounded-sm border border-slate-200/80 bg-white/80 px-2 py-1 text-[10px] text-slate-600">
                          <span className="font-semibold uppercase tracking-[0.12em] text-slate-500">
                            family counts
                          </span>
                          <div className="mt-1">{String(entry.details.family_counts)}</div>
                        </div>
                      ) : null}
                      {"family_groups" in entry.details ? (
                        <div className="mt-2 rounded-sm border border-slate-200/80 bg-white/80 px-2 py-1 text-[10px] text-slate-600">
                          <span className="font-semibold uppercase tracking-[0.12em] text-slate-500">
                            family groups
                          </span>
                          <div className="mt-1 break-words">{String(entry.details.family_groups)}</div>
                        </div>
                      ) : null}
                      <div className="mt-2 grid gap-1.5 text-[10px] text-slate-500">
                        {Object.entries(entry.details)
                          .filter(
                            ([key]) => key !== "subject"
                              && key !== "action"
                              && key !== "family"
                              && key !== "family_counts"
                              && key !== "family_groups",
                          )
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
                                            const command = key === "items"
                                              ? moduleShowCommand(moduleName)
                                              : moduleFocusCommand(moduleName);
                                            if (!command) return;
                                            runQuickCommand(command);
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
                            onClick={() => runQuickCommand(nativeStatusCommand)}
                            disabled={operatorPending}
                            className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                          >
                            refresh native
                          </button>
                          <button
                            type="button"
                            onClick={() => runQuickCommand(nativeReplayLastCommand)}
                            disabled={operatorPending}
                            className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                          >
                            replay last
                          </button>
                          <button
                            type="button"
                            onClick={() => runQuickCommand(nativeLastCommandQuery)}
                            disabled={operatorPending}
                            className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                          >
                            inspect last
                          </button>
                          {entry.details && "target" in entry.details && "command" in entry.details ? (
                            <button
                              type="button"
                              onClick={() => {
                                const replayCommand = `native replay ${String(entry.details?.target ?? "")} ${String(entry.details?.command ?? "")}${
                                  entry.details?.value ? ` ${String(entry.details.value)}` : ""
                                }`;
                                setOperatorCommand(replayCommand);
                              }}
                              disabled={operatorPending}
                              className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                            >
                              fill replay
                            </button>
                          ) : null}
                          {entry.details && "target" in entry.details && entry.details.target ? (
                            <button
                              type="button"
                              onClick={() => {
                                const focusCommand = `native focus ${String(entry.details?.target ?? "")}`;
                                runQuickCommand(focusCommand);
                              }}
                              disabled={operatorPending}
                              className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                            >
                              focus target
                            </button>
                          ) : null}
                          {"target" in entry.details && entry.details.target ? (
                            (() => {
                              const moduleName = String(entry.details.target);
                              const moduleShow = moduleShowCommand(moduleName);
                              const moduleInspectFill = moduleInspectFillCommand(moduleName);
                              return (
                                <>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      if (!moduleShow) return;
                                      runQuickCommand(moduleShow);
                                    }}
                                    disabled={operatorPending || !moduleShow}
                                    className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                                  >
                                    open module
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      if (!moduleInspectFill) return;
                                      setOperatorCommand(moduleInspectFill);
                                    }}
                                    disabled={operatorPending || !moduleInspectFill}
                                    className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                                  >
                                    fill inspect
                                  </button>
                                </>
                              );
                            })()
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
              <ConsoleBadge label="privilege" value={privilegePosture.roleLabel} tone={privilegeRole === "root" ? "emerald" : "amber"} />
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
                  <Row label="Execution" value={activeExecution?.chatId ?? "detached"} />
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
                    value={runtimeControl?.execution_gate?.reason ?? operatorReadyLabel}
                  />
                  <Row
                    label="Dispatch handoff"
                    value={diagnostics?.snapshot.dispatch_handoff_lane ?? "none"}
                  />
                  <Row
                    label="Tool families"
                    value={dispatchQueue?.family_counts ?? "none"}
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
                <Row label="Dispatch lane" value={diagnostics?.snapshot.dispatch_handoff_lane ?? "none"} />
                <Row
                  label="Contract"
                  value={`${diagnostics?.snapshot.dispatch_contract?.owner ?? "interactive"} / ${diagnostics?.snapshot.dispatch_contract?.mode ?? "direct"}`}
                />
                <Row
                  label="Takeover route"
                  value={
                    goalState?.active
                      ? (diagSubagentWorkers > 0 ? "goal + subagent warm handoff" : "goal lane warm handoff")
                      : "inspect before resume"
                  }
                />
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <ConsoleActionButton
                  action={inspectGoalAction}
                  pane="runtime"
                  label="inspect goal"
                  className="rounded-full border border-violet-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-violet-700 transition-colors hover:bg-violet-100"
                  disabled={operatorPending}
                  onRun={runContractAction}
                />
                <ConsoleActionButton
                  action={inspectContinuationAction}
                  pane="runtime"
                  label="inspect continuation"
                  className="rounded-full border border-violet-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-violet-700 transition-colors hover:bg-violet-100"
                  disabled={operatorPending}
                  onRun={runContractAction}
                />
                <ConsoleActionButton
                  action={resumeGoalAction}
                  pane="runtime"
                  label="resume goal"
                  className="rounded-full border border-violet-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-violet-700 transition-colors hover:bg-violet-100"
                  disabled={operatorPending}
                  onRun={runContractAction}
                />
                <ConsoleActionButton
                  action={completeGoalAction}
                  pane="runtime"
                  label="complete goal"
                  className="rounded-full border border-emerald-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-emerald-700 transition-colors hover:bg-emerald-100"
                  disabled={operatorPending}
                  onRun={runContractAction}
                />
                <ConsoleActionButton
                  action={cancelGoalAction}
                  pane="runtime"
                  label="cancel goal"
                  className="rounded-full border border-rose-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-rose-700 transition-colors hover:bg-rose-100"
                  disabled={operatorPending}
                  onRun={runContractAction}
                />
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
              <ConsoleRowGrid
                className="mt-2 grid gap-2 md:grid-cols-2"
                items={[
                  { label: "Session", value: activeExecution?.chatId ? "attached" : "detached" },
                  { label: "Goal state", value: goalState?.active ? "recoverable" : "idle" },
                  { label: "Dispatch backlog", value: `${diagnostics?.snapshot.dispatch_queue_depth ?? 0}` },
                  { label: "Handoff lane", value: diagnostics?.snapshot.dispatch_handoff_lane ?? "none" },
                  { label: "Subagent workers", value: `${diagSubagentWorkers}` },
                  { label: "Pending tools", value: `${diagPendingToolCalls}` },
                ]}
              />
              <div className="mt-3 flex flex-wrap gap-2">
                <ConsoleActionButton
                  action={inspectSessionAction}
                  pane="runtime"
                  label="inspect session"
                  className="rounded-full border border-emerald-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-emerald-700 transition-colors hover:bg-emerald-100"
                  disabled={operatorPending}
                  onRun={runContractAction}
                />
                <ConsoleActionButton
                  action={inspectContinuationAction}
                  pane="runtime"
                  label="inspect resume path"
                  className="rounded-full border border-emerald-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-emerald-700 transition-colors hover:bg-emerald-100"
                  disabled={operatorPending}
                  onRun={runContractAction}
                />
                <ConsoleActionButton
                  action={{ command: "tool status" }}
                  pane="runtime"
                  label="inspect backlog"
                  className="rounded-full border border-emerald-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-emerald-700 transition-colors hover:bg-emerald-100"
                  disabled={operatorPending}
                  onRun={() => runTopologyCommand("runtime", "tool status")}
                />
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
              <ConsoleRowGrid
                className="mt-2 grid gap-2 md:grid-cols-2"
                items={[
                  { label: "Depth", value: `${dispatchQueue?.depth ?? 0}` },
                  { label: "Lane", value: dispatchQueue?.lane ?? "interactive" },
                  { label: "Class", value: dispatchQueue?.job_class ?? "tool_contract_dispatch" },
                  { label: "Families", value: dispatchQueue?.family_counts ?? "none" },
                  { label: "Handoff", value: diagnostics?.snapshot.dispatch_handoff_lane ?? "none" },
                  { label: "Owner", value: dispatchQueue?.dispatch_contract?.owner ?? diagnostics?.snapshot.dispatch_contract?.owner ?? "interactive" },
                  { label: "Mode", value: dispatchQueue?.dispatch_contract?.mode ?? diagnostics?.snapshot.dispatch_contract?.mode ?? "direct" },
                ]}
              />
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
                <ConsoleActionButton
                  action={dispatchInspectAction}
                  pane="runtime"
                  label="inspect"
                  className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
                  disabled={operatorPending}
                  onRun={runContractAction}
                />
                {actionAllowed(dispatchPrioritizeAction) ? (
                  <>
                    {dispatchActionButtons.map(({ action, pane, label, className }) => (
                      <ConsoleActionButton
                        key={label}
                        action={action}
                        pane={pane}
                        label={label}
                        className={className}
                        disabled={operatorPending}
                        onRun={runContractAction}
                      />
                    ))}
                  </>
                ) : null}
              </div>
            </div>
            <div className="rounded-lg border border-cyan-200/80 bg-cyan-50/60 p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-cyan-700">
                  Privilege workflow
                </div>
                <ConsoleBadge
                  label="role"
                  value={privilegeRole}
                  tone={privilegeRole === "root" ? "emerald" : "amber"}
                />
              </div>
              <ConsoleRowGrid
                className="mt-2 grid gap-2 md:grid-cols-2"
                items={[
                  { label: "Session policy", value: privilegeWorkflow.sessionPolicy },
                  { label: "Elevation mode", value: privilegeWorkflow.mode },
                  { label: "Privileged controls", value: shellAllowsPrivilegedControls ? "contract-on" : "contract-off" },
                  { label: "Access posture", value: privilegePosture.accessLabel },
                  { label: "Elevate route", value: privilegeWorkflow.elevateHint },
                  { label: "Drop route", value: privilegeWorkflow.dropHint },
                ]}
              />
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => runQuickCommand("privilege status")}
                  className="rounded-full border border-cyan-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-cyan-700 transition-colors hover:bg-cyan-100"
                >
                  privilege status
                </button>
                {shellAllowsPrivilegedControls ? (
                  <button
                    type="button"
                    onClick={() => runQuickCommand("maintenance status")}
                    className="rounded-full border border-cyan-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-cyan-700 transition-colors hover:bg-cyan-100"
                  >
                    gated controls
                  </button>
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
                  <ConsoleBadge label="events" value={`${executionTimeline.length}`} tone="slate" />
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void handleTimelineRoute(faultLaneRoute)}
                    disabled={operatorPending || !faultLaneRoute?.command}
                    className="rounded-full border border-rose-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-rose-700 transition-colors hover:bg-rose-100"
                  >
                    fault lane {eventLaneCounts.fault}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleTimelineRoute(runtimeLaneRoute)}
                    disabled={operatorPending || !runtimeLaneRoute?.command}
                    className="rounded-full border border-cyan-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-cyan-700 transition-colors hover:bg-cyan-100"
                  >
                    runtime lane {eventLaneCounts.runtime}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleTimelineRoute(adapterLaneRoute)}
                    disabled={operatorPending || !adapterLaneRoute?.command}
                    className="rounded-full border border-amber-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-amber-700 transition-colors hover:bg-amber-100"
                  >
                    bridge lane {eventLaneCounts.bridge}
                  </button>
                </div>
                <div className="mt-3 space-y-2">
                  {executionTimeline.length ? executionTimeline.slice(0, 5).map((event, index) => (
                    <button
                      key={`${event.id ?? "event"}-${index}`}
                      type="button"
                      onClick={() => void handleTimelineRoute(event.route)}
                      disabled={operatorPending || !event.route?.command}
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
              )) : profile?.features?.slice(0, 6).map((feature) => (
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
                      tone="slate"
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
                        onClick={() => runContractAction(selectedModuleInspectNativeStatusAction, "adapters")}
                        disabled={operatorPending || !selectedModuleInspectNativeStatusAction?.command}
                        className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                      >
                        inspect native
                      </button>
                      {nativeLastCommand?.target === selectedModule.name ? (
                        <button
                          type="button"
                          onClick={() => runContractAction(nativeReplayLastAction, "adapters")}
                          disabled={operatorPending || !nativeReplayLastAction?.command}
                          className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                        >
                          replay native
                        </button>
                      ) : null}
                        <button
                          type="button"
                          onClick={() => {
                          const command = selectedModuleFocusNativeAction?.command;
                          if (!command) return;
                          runQuickCommand(command);
                        }}
                        disabled={operatorPending || !selectedModuleFocusNativeAction?.command}
                        className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                      >
                        native focus
                      </button>
                        <button
                          type="button"
                          onClick={() => {
                          const command = selectedModuleInspectNativeAction?.command;
                          if (!command) return;
                          runQuickCommand(command);
                        }}
                        disabled={operatorPending || !selectedModuleInspectNativeAction?.command}
                        className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                      >
                        native inspect
                      </button>
                        <button
                          type="button"
                          onClick={() => {
                          const command = selectedModuleShowModuleAction?.command;
                          if (!command) return;
                          runQuickCommand(command);
                        }}
                        disabled={operatorPending || !selectedModuleShowModuleAction?.command}
                        className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                      >
                        open module
                      </button>
                        <button
                          type="button"
                          onClick={() => {
                          const command = selectedModuleFillNativeReplayAction?.command;
                          if (!command) return;
                          setOperatorCommand(command);
                        }}
                        disabled={operatorPending || !selectedModuleFillNativeReplayAction?.command}
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
              {kernelManifest?.targets.runtime?.length ? kernelManifest.targets.runtime.slice(0, 4).map((target) => (
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
              {kernelManifest?.targets.languages?.length ? kernelManifest.targets.languages.slice(0, 4).map((language) => (
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
            <ConsoleRowGrid
              items={[
                { label: "Adapter", value: selectedBridge?.adapter ?? (runtimeControl?.active_adapter ?? "unset") },
                { label: "Health", value: selectedBridge?.health ?? "unknown" },
                { label: "Status", value: selectedBridge?.status ?? "unknown" },
                { label: "Maintenance", value: runtimeControl?.maintenance_mode?.enabled ? "enabled" : "off" },
              ]}
            />
            <div className="flex flex-wrap gap-2">
              <ConsoleActionButton
                action={selectedBridgeInspectAction}
                pane="adapters"
                label="inspect"
                className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
                disabled={operatorPending}
                onRun={runContractAction}
              />
              {actionAllowed(selectedBridgeRestartAction) ? (
                <>
                  {bridgeActionButtons.map(({ action, pane, label, className }) => (
                    <ConsoleActionButton
                      key={label}
                      action={action}
                      pane={pane}
                      label={label}
                      className={className}
                      disabled={operatorPending}
                      onRun={runContractAction}
                    />
                  ))}
                </>
              ) : selectedBridgeRestartAction ? (
                <span className="text-xs text-muted-foreground">
                  {bridgeRestrictionHint}
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
              {adapterContract?.transport_modes?.length ? adapterContract.transport_modes.slice(0, 5).map((transport) => (
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
              {adapterContract?.control_plane?.length ? adapterContract.control_plane.slice(0, 5).map((item) => (
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
                  <Row label="Stage" value={bridge.runtime_stage ?? "unknown"} />
                  <Row label="Mode" value={bridge.runtime_mode ?? "unknown"} />
                  <Row label="ABI" value={bridge.abi ?? "unknown"} />
                  <Row label="Artifact" value={bridge.manifest ?? bridge.entrypoint ?? "unknown"} />
                </div>
                {(bridge.runtime || bridge.version || bridge.queue_depth !== undefined || bridge.module_count !== undefined || bridge.updated_at_ms !== undefined) ? (
                  <div className="mt-2 grid gap-2 md:grid-cols-4">
                    {bridge.runtime ? <Row label="Runtime" value={bridge.runtime} /> : null}
                    {bridge.version ? <Row label="Version" value={bridge.version} /> : null}
                    {bridge.queue_depth !== undefined ? <Row label="Queue depth" value={String(bridge.queue_depth ?? 0)} /> : null}
                    {bridge.module_count !== undefined ? <Row label="Module count" value={String(bridge.module_count ?? 0)} /> : null}
                    {bridge.updated_at_ms !== undefined ? <Row label="Updated" value={formatKernelTimestamp(bridge.updated_at_ms)} /> : null}
                  </div>
                ) : null}
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
                {bridge.manifest || bridge.status_symbol || bridge.build_hint || bridge.kernel_surface || bridge.free_symbol || bridge.attach_symbol || bridge.capabilities?.length ? (
                  <div className="mt-3 grid gap-2 rounded-md border border-slate-200/80 bg-white/80 p-3 text-xs">
                    {bridge.manifest ? (
                      <Row label="Manifest" value={bridge.manifest} />
                    ) : null}
                    {bridge.kernel_surface ? (
                      <Row label="Kernel surface" value={bridge.kernel_surface} />
                    ) : null}
                    {bridge.runtime_mode ? (
                      <Row label="Runtime mode" value={bridge.runtime_mode} />
                    ) : null}
                    {bridge.status_symbol ? (
                      <Row label="Status symbol" value={bridge.status_symbol} />
                    ) : null}
                    {bridge.free_symbol ? (
                      <Row label="Free symbol" value={bridge.free_symbol} />
                    ) : null}
                    {bridge.attach_symbol ? (
                      <Row label="Attach symbol" value={bridge.attach_symbol} />
                    ) : null}
                    {bridge.capabilities?.length ? (
                      <Row label="Capabilities" value={bridge.capabilities.join(", ")} />
                    ) : null}
                    {bridge.module_states ? (
                      <Row
                        label="Module states"
                        value={Object.entries(bridge.module_states)
                          .map(([name, row]) => `${name}:${row?.status ?? "unknown"}:${row?.last_code ?? 0}`)
                          .join(", ")}
                      />
                    ) : null}
                    {bridge.last_command ? (
                      <Row
                        label="Last command"
                        value={formatBridgeCommandSummary(bridge.last_command)}
                      />
                    ) : null}
                    {bridge.recent_commands?.length ? (
                      <div className="grid gap-2">
                        <div className="font-medium uppercase tracking-[0.18em] text-slate-500">
                          Recent commands
                        </div>
                        <div className="grid gap-2">
                          {bridge.recent_commands.map((row, index) => (
                            <div
                              key={`${bridge.adapter}-recent-command-${index}`}
                              className="grid gap-1 rounded-md border border-slate-200/80 bg-slate-50/90 px-3 py-2"
                            >
                              <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                                <span>{row.target ?? "runtime"}</span>
                                <span>{row.action ?? "status"}</span>
                              </div>
                              <div className="flex flex-wrap items-center gap-2 text-[12px] text-slate-700">
                                <span>{formatBridgeCommandSummary(row)}</span>
                                {typeof row.updated_at_ms === "number" ? (
                                  <span>{formatKernelTimestamp(row.updated_at_ms)}</span>
                                ) : null}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
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
                      onTrigger: () => {
                        const restartCommand = `restart-bridge ${bridge.adapter}`;
                        runQuickCommand(restartCommand);
                      },
                    }}
                  />
                  <AdapterActionButton
                    binding={{
                      ...resolveActionBinding("record_fault"),
                      onTrigger: () => {
                        const recordFaultCommand = `record-fault fault ${bridge.adapter}`;
                        runQuickCommand(recordFaultCommand);
                      },
                    }}
                  />
                  {bridge.health === "fault" ? (
                    <AdapterActionButton
                      binding={{
                        ...resolveActionBinding("clear_fault"),
                        onTrigger: () => {
                          const clearFaultCommand = `clear-fault ${bridge.adapter}`;
                          runQuickCommand(clearFaultCommand);
                        },
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
            {profile?.tools?.length ? profile.tools.slice(0, 6).map((tool) => (
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
            <ConsoleRowGrid items={runtimeSummaryRows} className="grid gap-2" />
          </div>
          <div className="grid gap-3 rounded-xl border border-border/70 bg-background/80 p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                Native control
              </div>
              <ConsoleBadge
                label="queue"
                value={`${nativeQueueDepth(nativeSnapshot)}`}
                tone={nativeQueueDepth(nativeSnapshot) ? "amber" : "slate"}
              />
            </div>
            <ConsoleRowGrid
              items={buildNativeControlRows({
                nativeLastCommand,
                lastNativeContext,
                nativeSnapshot,
                moduleFocus: runtimeControl?.module_focus,
              })}
            />
            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500">Native modules</div>
              <div className="flex flex-wrap gap-2">
                {nativeModuleEntries.length ? nativeModuleEntries.slice(0, 8).map(([name, state]) => (
                  <div key={name}>
                    {renderNativeModuleChip({
                      name,
                      state,
                      operatorPending,
                      pane: "modules",
                      className: "rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100",
                      label: `${name}:${state?.status ?? "unknown"}`,
                      onRun: runContractAction,
                    })}
                  </div>
                )) : (
                  renderConsoleEmptyState("No native modules observed.")
                )}
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500">Recent commands</div>
              <div className="flex flex-wrap gap-2">
                {nativeSnapshot?.recent_commands?.length ? nativeSnapshot.recent_commands.slice(-6).reverse().map((command, index) => (
                  <div key={`${command.updated_at_ms ?? "native"}-${command.target ?? "target"}-${command.action ?? index}`}>
                    {renderNativeCommandChip({
                      command,
                      index,
                      operatorPending,
                      onRun: runContractAction,
                    })}
                  </div>
                )) : (
                  renderConsoleEmptyState("No recent native commands.")
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {nativeActionButtons.map(({ action, pane, label, className }) => (
                <ConsoleActionButton
                  key={label}
                  action={action}
                  pane={pane}
                  label={label}
                  className={className}
                  disabled={operatorPending}
                  onRun={runContractAction}
                />
              ))}
              {nativeLastCommand?.target && nativeLastCommand?.action ? (
                <>
                  {nativeLastTargetActionButtons.map(({ action, pane, label, className }) => (
                    <ConsoleActionButton
                      key={label}
                      action={action}
                      pane={pane}
                      label={label}
                      className={className}
                      disabled={operatorPending}
                      onRun={runContractAction}
                    />
                  ))}
                </>
              ) : clearFaultsAction ? (
                <span className="text-xs text-muted-foreground">
                  {clearFaultRestrictionHint}
                </span>
              ) : null}
              {selectedModule?.name ? (
                <>
                  {selectedNativeModuleActionButtons.map(({ action, pane, label, className }) => (
                    <ConsoleActionButton
                      key={label}
                      action={action}
                      pane={pane}
                      label={label}
                      className={className}
                      disabled={operatorPending}
                      onRun={runContractAction}
                    />
                  ))}
                  <button
                    type="button"
                    onClick={() => {
                      const command = selectedModuleFillNativeInspectAction?.command;
                      if (!command) return;
                      setOperatorCommand(command);
                    }}
                    disabled={operatorPending || !selectedModuleFillNativeInspectAction?.command}
                    className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                  >
                    fill selected inspect
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const command = selectedModuleFillNativeReplayAction?.command;
                      if (!command) return;
                      setOperatorCommand(command);
                    }}
                    disabled={operatorPending || !selectedModuleFillNativeReplayAction?.command}
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
                {runtimeTopologyAdapters.length ? runtimeTopologyAdapters.map((adapter) => {
                  const inspectAdapterAction = adapter.actions?.find((action) => action.id === "inspect_adapter");
                  return (
                    <button
                      key={adapter.name}
                      type="button"
                      onClick={() => {
                        onSelectAdapter(adapter.name);
                        runContractAction(inspectAdapterAction, "adapters");
                      }}
                      disabled={operatorPending || !inspectAdapterAction?.command}
                      className="rounded-full border border-emerald-300/80 bg-emerald-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-emerald-700 transition-colors hover:bg-emerald-100"
                    >
                      {adapter.name}
                    </button>
                  );
                }) : (
                  <span className="text-xs text-muted-foreground">No adapter topology exposed.</span>
                )}
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500">Lanes</div>
              <div className="flex flex-wrap gap-2">
                {runtimeTopologyLanes.length ? runtimeTopologyLanes.map((lane) => {
                  const openLaneAction = lane.actions?.find((action) => action.id === "open_lane");
                  return (
                    <button
                      key={lane.id}
                      type="button"
                      onClick={() => runContractAction(openLaneAction, "runtime")}
                      disabled={operatorPending || !openLaneAction?.command}
                      className="rounded-full border border-blue-300/80 bg-blue-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-blue-700 transition-colors hover:bg-blue-100"
                    >
                      {lane.id}
                    </button>
                  );
                }) : (
                  <span className="text-xs text-muted-foreground">No lane topology exposed.</span>
                )}
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500">Modules</div>
              <div className="flex flex-wrap gap-2">
                {runtimeTopologyModules.length ? runtimeTopologyModules.map((module) => {
                  const showModuleAction = module.actions?.find((action) => action.id === "show_module");
                  const focusNativeAction = module.actions?.find((action) => action.id === "focus_native");
                  return (
                    <div key={module.name} className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => {
                          onSelectModule(module.name);
                          runContractAction(showModuleAction, "modules");
                        }}
                        disabled={operatorPending || !showModuleAction?.command}
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
                          onClick={() => runContractAction(focusNativeAction, "modules")}
                          disabled={operatorPending || !focusNativeAction?.command}
                          className="rounded-full border border-fuchsia-300/80 bg-fuchsia-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-fuchsia-700 transition-colors hover:bg-fuchsia-100"
                        >
                          inspect
                        </button>
                      ) : null}
                    </div>
                  );
                }) : (
                  <span className="text-xs text-muted-foreground">No module topology exposed.</span>
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => runContractAction(inspectRuntimeAction, "runtime")}
                disabled={operatorPending || !inspectRuntimeAction?.command}
                className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
              >
                inspect runtime
              </button>
              <button
                type="button"
                onClick={() => runContractAction(runtimeOrchestrationAction, "runtime")}
                disabled={operatorPending || !runtimeOrchestrationAction?.command}
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
                      onSelectPane(embeddedBoardStatusAction?.pane ?? "adapters");
                      onSelectBoardPort?.(port);
                      runContractAction(embeddedBoardStatusAction, "adapters");
                    }}
                    disabled={operatorPending || !embeddedBoardStatusAction?.command}
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
                  {privilegePosture.accessLabel}
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
                onClick={() => runContractAction(embeddedInspectAction, "runtime")}
                disabled={operatorPending || !embeddedInspectAction?.command}
                className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
              >
                inspect embedded
              </button>
              <button
                type="button"
                onClick={() => runContractAction(embeddedRefreshPortsAction, "adapters")}
                disabled={operatorPending || !embeddedRefreshPortsAction?.command}
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
                    {Array.isArray(queue.family_rows) && queue.family_rows.length ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {queue.family_rows.map((entry) => (
                          <span
                            key={`${queue.id}-${entry.family}`}
                            className="rounded-full border border-amber-300/80 bg-amber-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-amber-700"
                          >
                            {entry.family}:{entry.count}
                          </span>
                        ))}
                      </div>
                    ) : queue.family_counts && queue.family_counts !== "none" ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {String(queue.family_counts).split(",").map((entry) => (
                          <span
                            key={`${queue.id}-${entry}`}
                            className="rounded-full border border-amber-300/80 bg-amber-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-amber-700"
                          >
                            {entry.trim()}
                          </span>
                        ))}
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
                          (() => {
                            const familyMatch = task.match(/\[([^\]]+)\]/);
                            const family = familyMatch?.[1] ?? "";
                            return (
                          <button
                            key={task}
                            type="button"
                            onClick={() => {
                              if (task.startsWith("dispatch:")) {
                                runContractAction(dispatchInspectAction, "runtime");
                                return;
                              }
                              if (queue.lane === "subagent") {
                                runContractAction(kernelManifest?.worker_controls?.actions?.[0], "runtime");
                                return;
                              }
                              if (queue.lane === "sustained_goal") {
                                runContractAction(sessionControls[1], "runtime");
                                return;
                              }
                            }}
                            disabled={operatorPending}
                            className={cn(
                              "rounded-full border px-2 py-0.5 text-[11px] transition-colors hover:brightness-[0.98]",
                              toolFamilyChipTone(family),
                            )}
                          >
                            {task.replace("dispatch:", "")}
                          </button>
                            );
                          })()
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
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              {toolFamilySurface.map((item) => (
                <div
                  key={`workspace-${item.family}`}
                  className="rounded-md border border-slate-200/80 bg-slate-50/80 px-2.5 py-2"
                >
                  <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                    {item.family}
                  </div>
                  <div className="mt-1 text-[10px] text-slate-600">
                    {item.examples}
                  </div>
                </div>
              ))}
            </div>
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
                {nativeFaultModules.length ? nativeFaultModules.slice(0, 6).map(([name, state]) => {
                  return (
                    <div key={name}>
                      {renderNativeModuleChip({
                        name,
                        state,
                        operatorPending,
                        pane: "modules",
                        className: "rounded-full border border-rose-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-rose-700 transition-colors hover:bg-rose-100",
                        label: `${name}:${state?.last_code ?? 0}`,
                        onRun: runContractAction,
                      })}
                    </div>
                  );
                }) : (
                  renderConsoleEmptyState("No native module faults.", "text-xs text-rose-700/80")
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
                {faultedBridges.length ? faultedBridges.slice(0, 6).map((bridge) => {
                  const inspectBridgeAction = bridge.actions?.find((action) => action.id === "inspect_bridge");
                  return (
                    <button
                      key={bridge.adapter}
                      type="button"
                      onClick={() => runContractAction(inspectBridgeAction, "adapters")}
                      disabled={operatorPending || !inspectBridgeAction?.command}
                      className="rounded-full border border-amber-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-amber-700 transition-colors hover:bg-amber-100"
                    >
                      {bridge.adapter}:{bridge.runtime_stage ?? bridge.health}
                    </button>
                  );
                }) : (
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
                  (() => {
                    const route = shellErrorTriageById[error.id];
                    return (
                      <button
                        key={error.id}
                        type="button"
                        onClick={() => {
                          if (route) {
                            runTopologyCommand(route.pane, route.command);
                            return;
                          }
                          runContractAction(inspectFaultsAction, "faults");
                        }}
                        disabled={operatorPending || (!route && !inspectFaultsAction?.command)}
                        className="rounded-full border border-violet-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-violet-700 transition-colors hover:bg-violet-100"
                      >
                        {error.kind}
                      </button>
                    );
                  })()
                )) : (
                  <span className="text-xs text-violet-700/80">No shell errors.</span>
                )}
              </div>
            </div>
          </div>
          <div className="rounded-xl border border-border/70 bg-background/80 p-3">
            <ConsoleRowGrid items={faultSummaryRows} className="mb-3 grid gap-2 md:grid-cols-2" />
            <div className="mb-3 grid gap-3 md:grid-cols-3">
              <ConsoleInfoCard
                label="Privilege gate"
                value={privilegePosture.recoveryLabel}
                className="rounded-lg border border-slate-200/80 bg-white/80 p-3"
                labelClassName="text-[10px] uppercase tracking-[0.14em] text-slate-500"
                valueClassName="mt-2 text-sm font-semibold text-slate-950"
              />
              <ConsoleInfoCard
                label="Escalation path"
                value={runtimeControl?.fault_posture.supervisor ?? diagnostics?.supervisor ?? "kernel-supervisor"}
                className="rounded-lg border border-rose-200/80 bg-rose-50/80 p-3"
                labelClassName="text-[10px] uppercase tracking-[0.14em] text-rose-700"
                valueClassName="mt-2 text-sm font-semibold text-rose-950"
              />
              <ConsoleInfoCard
                label="Recommended move"
                value={recentErrors.length || nativeFaultModules.length || faultedBridges.length ? "inspect then clear" : "hold steady"}
                className="rounded-lg border border-amber-200/80 bg-amber-50/80 p-3"
                labelClassName="text-[10px] uppercase tracking-[0.14em] text-amber-700"
                valueClassName="mt-2 text-sm font-semibold text-amber-950"
              />
            </div>
            {faultFocusModule ? (
              <div className="mb-3 rounded-lg border border-rose-200/80 bg-rose-50/80 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.14em] text-rose-700">Fault focus module</div>
                    <div className="mt-1 text-sm font-semibold text-rose-950">{faultFocusModule.name}</div>
                  </div>
                  <span className="rounded-full border border-rose-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-rose-700">
                    module-linked
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {faultFocusModule.focus ? (
                    <button
                      type="button"
                      onClick={() => runQuickCommand(faultFocusModule.focus!)}
                      disabled={operatorPending}
                      className="rounded-full border border-rose-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-rose-700 transition-colors hover:bg-rose-100"
                    >
                      focus module
                    </button>
                  ) : null}
                  {faultFocusModule.show ? (
                    <button
                      type="button"
                      onClick={() => runQuickCommand(faultFocusModule.show!)}
                      disabled={operatorPending}
                      className="rounded-full border border-rose-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-rose-700 transition-colors hover:bg-rose-100"
                    >
                      open module
                    </button>
                  ) : null}
                  {faultFocusModule.inspect ? (
                    <button
                      type="button"
                      onClick={() => setOperatorCommand(faultFocusModule.inspect!)}
                      disabled={operatorPending}
                      className="rounded-full border border-rose-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-rose-700 transition-colors hover:bg-rose-100"
                    >
                      fill inspect
                    </button>
                  ) : null}
                </div>
              </div>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <ConsoleActionButton
                action={inspectFaultsAction}
                pane="faults"
                label="inspect"
                className="rounded-full border border-slate-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-700 transition-colors hover:bg-slate-50"
                disabled={operatorPending}
                onRun={runContractAction}
              />
              {actionAllowed(clearFaultsAction) ? (
                <>
                  {faultActionButtons.map(({ action, pane, label, className }) => (
                    <ConsoleActionButton
                      key={label}
                      action={action}
                      pane={pane}
                      label={label}
                      className={className}
                      disabled={operatorPending}
                      onRun={runContractAction}
                    />
                  ))}
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
                        {formatKernelTimestamp(error.at)}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-rose-900">{error.message}</div>
                    {shellErrorTriageById[error.id] ? (
                      <div className="mt-2">
                        <button
                          type="button"
                          onClick={() => runTopologyCommand(
                            shellErrorTriageById[error.id].pane,
                            shellErrorTriageById[error.id].command,
                          )}
                          disabled={operatorPending}
                          className="rounded-full border border-rose-300/80 bg-white px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-rose-700 transition-colors hover:bg-rose-50"
                        >
                          triage in {shellErrorTriageById[error.id].pane}
                        </button>
                      </div>
                    ) : null}
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
            {executionTimeline.length ? (
              <div className="space-y-2">
                {executionTimeline.map((event) => (
                  <div
                    key={event.id}
                    className="rounded-md border border-slate-200/80 bg-slate-50/80 px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-700">
                        {event.type}
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
              {embeddedTargetHint ?? "Universal execution kernel with desktop, service, and embedded headroom"}
            </div>
            {runtimeControl ? (
              <div className="mt-2 grid gap-2 rounded-md border border-slate-300/70 bg-slate-50/80 p-3">
                <Row label="Active adapter" value={runtimeControl?.active_adapter ?? "unset"} />
                <Row label="Execution gate" value={runtimeControl.execution_gate?.state ?? "open"} />
                <Row
                  label="Gate reason"
                  value={runtimeControl.execution_gate?.reason ?? operatorReadyLabel}
                />
                <Row
                  label="Maintenance"
                  value={runtimeControl.maintenance_mode?.enabled ? "enabled" : "off"}
                />
                <Row label="Privilege role" value={privilegePosture.roleLabel} />
                <Row label="Control posture" value={privilegePosture.accessLabel} />
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
              Mira keeps the shell thin and the kernel visible, so the same operator surface can supervise
              desktop runtime faults, service modules, firmware flows, and board-level automation without
              turning the core into product-specific UI code.
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

function ConsoleInfoCard({
  label,
  value,
  detail,
  className,
  labelClassName,
  valueClassName,
  detailClassName,
}: {
  label: string;
  value: string;
  detail?: string;
  className: string;
  labelClassName: string;
  valueClassName: string;
  detailClassName?: string;
}) {
  return (
    <div className={className}>
      <div className={labelClassName}>{label}</div>
      <div className={valueClassName}>{value}</div>
      {detail ? (
        <div className={detailClassName ?? "mt-1 text-xs text-slate-500"}>
          {detail}
        </div>
      ) : null}
    </div>
  );
}

function ConsoleRowGrid({
  items,
  className = "grid gap-2 md:grid-cols-2",
}: {
  items: Array<{ label: string; value: string }>;
  className?: string;
}) {
  return (
    <div className={className}>
      {items.map((item) => (
        <Row key={`${item.label}:${item.value}`} label={item.label} value={item.value} />
      ))}
    </div>
  );
}

function ConsoleActionButton({
  action,
  pane,
  label,
  className,
  disabled,
  onRun,
}: {
  action?: { command?: string | null } | null;
  pane: string;
  label: string;
  className: string;
  disabled: boolean;
  onRun: (action: { command?: string | null } | null | undefined, pane: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onRun(action, pane)}
      disabled={disabled || !action?.command}
      className={className}
    >
      {label}
    </button>
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
