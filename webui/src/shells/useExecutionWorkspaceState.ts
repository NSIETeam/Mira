import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchWorkspaces } from "@/lib/api";
import type {
  ExecutionSummary,
  WorkspaceScopePayload,
  WorkspacesPayload,
} from "@/lib/types";
import { projectNameFromPath } from "@/lib/workspace";
import type { ShellRoute } from "@/shells/host";

interface UseExecutionWorkspaceStateOptions {
  token: string;
  activeExecutionId: string | null;
  activeExecution: ExecutionSummary | null;
  activeExecutionRunning: boolean;
  createExecution: (
    workspaceScope?: WorkspaceScopePayload | null,
  ) => Promise<string>;
  navigate: (route: ShellRoute, options?: { replace?: boolean }) => void;
  setMobileSidebarOpen: React.Dispatch<React.SetStateAction<boolean>>;
  client: {
    setWorkspaceScope: (chatId: string, scope: WorkspaceScopePayload) => void;
  };
  onNewExecution: () => void;
  onWorkspaceScopeRejected: string;
}

export function normalizeWorkspaceScope(
  scope: WorkspaceScopePayload,
): WorkspaceScopePayload {
  const accessMode = scope.access_mode === "restricted" ? "restricted" : "full";
  return {
    ...scope,
    project_name: scope.project_name ?? projectNameFromPath(scope.project_path),
    access_mode: accessMode,
    restrict_to_workspace: accessMode === "restricted",
  };
}

export function useExecutionWorkspaceState({
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
}: UseExecutionWorkspaceStateOptions) {
  const [workspaces, setWorkspaces] = useState<WorkspacesPayload | null>(null);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [draftWorkspaceScope, setDraftWorkspaceScope] =
    useState<WorkspaceScopePayload | null>(null);
  const [workspaceOverrides, setWorkspaceOverrides] =
    useState<Record<string, WorkspaceScopePayload>>({});

  const refreshWorkspaces = useCallback(async () => {
    try {
      const payload = await fetchWorkspaces(token);
      setWorkspaces(payload);
    } catch {
      setWorkspaces(null);
    }
  }, [token]);

  useEffect(() => {
    void refreshWorkspaces();
  }, [refreshWorkspaces]);

  const activeWorkspaceScope = useMemo<WorkspaceScopePayload | null>(() => {
    if (activeExecutionId && workspaceOverrides[activeExecutionId]) {
      return workspaceOverrides[activeExecutionId];
    }
    if (activeExecution?.workspaceScope) {
      return activeExecution.workspaceScope;
    }
    return draftWorkspaceScope ?? workspaces?.default_scope ?? null;
  }, [
    activeExecution?.workspaceScope,
    activeExecutionId,
    draftWorkspaceScope,
    workspaceOverrides,
    workspaces?.default_scope,
  ]);

  const applyWorkspaceScope = useCallback(
    (scope: WorkspaceScopePayload) => {
      const next = normalizeWorkspaceScope(scope);
      setWorkspaceError(null);
      if (activeExecutionId) {
        if (!activeExecutionRunning) {
          client.setWorkspaceScope(activeExecutionId, next);
        }
        return;
      }
      setDraftWorkspaceScope(next);
    },
    [activeExecutionId, activeExecutionRunning, client],
  );

  const onCreateExecution = useCallback(
    async (workspaceScope?: WorkspaceScopePayload | null) => {
      try {
        const scope = workspaceScope ?? activeWorkspaceScope;
        const executionId = await createExecution(scope);
        navigate({
          view: "chat",
          activeKey: `websocket:${executionId}`,
          settingsSection: "overview",
        });
        setMobileSidebarOpen(false);
        if (scope) {
          setWorkspaceOverrides((current) => ({
            ...current,
            [executionId]: normalizeWorkspaceScope(scope),
          }));
        }
        return executionId;
      } catch (e) {
        console.error("Failed to create execution", e);
        if (e instanceof Error && e.message.startsWith("workspace_scope_rejected:")) {
          setWorkspaceError(onWorkspaceScopeRejected);
        }
        return null;
      }
    },
    [
      activeWorkspaceScope,
      createExecution,
      navigate,
      onWorkspaceScopeRejected,
      setMobileSidebarOpen,
    ],
  );

  const onNewExecutionInProject = useCallback(
    (projectPath: string, projectName: string) => {
      const base = workspaces?.default_scope ?? activeWorkspaceScope;
      const trimmed = projectPath.trim();
      if (!base || !trimmed) {
        onNewExecution();
        return;
      }
      navigate({
        view: "chat",
        activeKey: null,
        settingsSection: "overview",
      });
      setDraftWorkspaceScope(
        normalizeWorkspaceScope({
          project_path: trimmed,
          project_name: projectName || projectNameFromPath(trimmed),
          access_mode: base.access_mode,
          restrict_to_workspace: base.access_mode === "restricted",
        }),
      );
      setWorkspaceError(null);
      setMobileSidebarOpen(false);
    },
    [
      activeWorkspaceScope,
      navigate,
      onNewExecution,
      setMobileSidebarOpen,
      workspaces?.default_scope,
    ],
  );

  return {
    workspaces,
    workspaceError,
    draftWorkspaceScope,
    workspaceOverrides,
    activeWorkspaceScope,
    refreshWorkspaces,
    applyWorkspaceScope,
    onCreateExecution,
    onNewExecutionInProject,
    setWorkspaceError,
    setDraftWorkspaceScope,
    setWorkspaceOverrides,
  };
}
