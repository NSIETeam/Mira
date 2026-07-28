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
  handlers,
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
  handlers: Record<string, (() => void) | undefined>;
}) {
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
