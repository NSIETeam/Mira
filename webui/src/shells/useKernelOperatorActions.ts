export interface KernelOperatorActionBinding {
  id: string;
  label: string;
  kind?: string;
  availability?: string;
  targetPane?: string | null;
  privileged?: boolean;
  requiredRole?: string | null;
  privilegedReason?: string | null;
  enabled: boolean;
  onTrigger?: () => void;
}

export function useKernelOperatorActions({
  actionRegistry,
  onOpenKernelSettings,
  onRestartRuntime,
  onRestartEngine,
  onInspectFaults,
  onRecordFault,
  onClearFault,
  onRestartBridge,
  onPauseRuntime,
  onResumeRuntime,
  onDegradeRuntime,
  onDrainBackground,
  onPrioritizeGoalLane,
  onEnterMaintenance,
  onExitMaintenance,
  onInspectModules,
  onSwitchAdapter,
  onAttachBoard,
}: {
  actionRegistry: Array<{
    id: string;
    label: string;
    kind: string;
    availability?: string;
    target_pane?: string | null;
    privileged?: boolean;
    required_role?: string | null;
    privileged_reason?: string | null;
  }>;
  onOpenKernelSettings?: () => void;
  onRestartRuntime?: () => void;
  onRestartEngine?: () => void;
  onInspectFaults?: () => void;
  onRecordFault?: () => void;
  onClearFault?: () => void;
  onRestartBridge?: () => void;
  onPauseRuntime?: () => void;
  onResumeRuntime?: () => void;
  onDegradeRuntime?: () => void;
  onDrainBackground?: () => void;
  onPrioritizeGoalLane?: () => void;
  onEnterMaintenance?: () => void;
  onExitMaintenance?: () => void;
  onInspectModules?: () => void;
  onSwitchAdapter?: () => void;
  onAttachBoard?: () => void;
}) {
  const handlers: Record<string, (() => void) | undefined> = {
    open_kernel_settings: onOpenKernelSettings,
    restart_runtime: onRestartRuntime,
    restart_engine: onRestartEngine,
    inspect_faults: onInspectFaults,
    record_fault: onRecordFault,
    clear_fault: onClearFault,
    restart_bridge: onRestartBridge,
    pause_runtime: onPauseRuntime,
    resume_runtime: onResumeRuntime,
    degrade_runtime: onDegradeRuntime,
    drain_background: onDrainBackground,
    prioritize_goal_lane: onPrioritizeGoalLane,
    enter_maintenance: onEnterMaintenance,
    exit_maintenance: onExitMaintenance,
    inspect_modules: onInspectModules,
    switch_adapter: onSwitchAdapter,
    attach_board: onAttachBoard,
  };
  const bindings = actionRegistry.map<KernelOperatorActionBinding>((action) => ({
    id: action.id,
    label: action.label,
    kind: action.kind,
    availability: action.availability,
    targetPane: action.target_pane ?? null,
    privileged: action.privileged ?? false,
    requiredRole: action.required_role ?? null,
    privilegedReason: action.privileged_reason ?? null,
    enabled: typeof handlers[action.id] === "function",
    onTrigger: handlers[action.id],
  }));
  return {
    byId: Object.fromEntries(bindings.map((binding) => [binding.id, binding])),
  };
}
