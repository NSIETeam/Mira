import { useCallback, useMemo } from "react";

import type { ExecutionSummary, WorkspaceScopePayload } from "@/lib/types";
import type { ShellRoute } from "@/shells/host";

interface UseEngineeringSidebarStateOptions {
  sessions: ExecutionSummary[];
  executions: ExecutionSummary[];
  activeKey: string | null;
  loading: boolean;
  activeShellView: "chat" | "settings" | "apps" | "automations" | "skills";
  sidebarState: {
    pinned_keys: string[];
    archived_keys: string[];
    title_overrides: Record<string, string>;
    project_name_overrides: Record<string, string>;
    collapsed_groups: Record<string, boolean>;
    view: {
      density?: "comfortable" | "compact";
      show_previews?: boolean;
      show_timestamps?: boolean;
      show_archived: boolean;
      sort?: "updated_desc" | "created_desc" | "title_asc";
    };
  };
  updateSidebarState: (updater: (current: any) => any) => Promise<any> | void;
  navigate: (route: ShellRoute, options?: { replace?: boolean }) => void;
  setUpdatedExecutionIds: React.Dispatch<React.SetStateAction<Set<string>>>;
  setDraftWorkspaceScope: React.Dispatch<React.SetStateAction<WorkspaceScopePayload | null>>;
  setWorkspaceError: React.Dispatch<React.SetStateAction<string | null>>;
  setMobileSidebarOpen: React.Dispatch<React.SetStateAction<boolean>>;
  normalizeWorkspaceScope: (scope: WorkspaceScopePayload) => WorkspaceScopePayload;
  onNewExecution: () => void;
  onRequestDelete: (key: string, label: string) => void;
  onRequestRename: (key: string, label: string) => void;
  onToggleArchive: (key: string) => void;
  onRequestRenameProject: (key: string, label: string) => void;
  onNewExecutionInProject: (projectPath: string, projectName: string) => void;
  onOpenSettings: (section?: any) => void;
  onOpenApps: () => void;
  onOpenAutomations: () => void;
  onOpenSkills: () => void;
  onSettingsIntent: () => void;
  onOpenSessionSearch: () => void;
  runningExecutionIdList: string[];
  updatedExecutionIdList: string[];
  defaultWorkspacePath: string | null;
}

export function useEngineeringSidebarState({
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
  defaultWorkspacePath,
}: UseEngineeringSidebarStateOptions) {
  const onSelectExecution = useCallback(
    (key: string) => {
      const selected = sessions.find((session) => session.key === key);
      const selectedExecutionId = selected?.chatId;
      if (selectedExecutionId) {
        setUpdatedExecutionIds((current) => {
          if (!current.has(selectedExecutionId)) return current;
          const next = new Set(current);
          next.delete(selectedExecutionId);
          return next;
        });
      }
      if (selected?.workspaceScope) {
        setDraftWorkspaceScope(normalizeWorkspaceScope(selected.workspaceScope));
      } else {
        setDraftWorkspaceScope(null);
      }
      setWorkspaceError(null);
      navigate({ view: "chat", activeKey: key, settingsSection: "overview" });
      setMobileSidebarOpen(false);
    },
    [
      navigate,
      normalizeWorkspaceScope,
      sessions,
      setDraftWorkspaceScope,
      setMobileSidebarOpen,
      setUpdatedExecutionIds,
      setWorkspaceError,
    ],
  );

  const onTogglePin = useCallback(
    (key: string) => {
      void updateSidebarState((current) => {
        const pinned = new Set(current.pinned_keys);
        if (pinned.has(key)) pinned.delete(key);
        else pinned.add(key);
        return {
          ...current,
          pinned_keys: Array.from(pinned),
        };
      });
    },
    [updateSidebarState],
  );

  const onToggleGroup = useCallback(
    (groupId: string) => {
      void updateSidebarState((current) => {
        const collapsedGroups = { ...current.collapsed_groups };
        if (groupId === "workspace:chats" || groupId === "date:all") {
          if (collapsedGroups[groupId] === false) delete collapsedGroups[groupId];
          else collapsedGroups[groupId] = false;
          return {
            ...current,
            collapsed_groups: collapsedGroups,
          };
        }
        if (collapsedGroups[groupId]) delete collapsedGroups[groupId];
        else collapsedGroups[groupId] = true;
        return {
          ...current,
          collapsed_groups: collapsedGroups,
        };
      });
    },
    [updateSidebarState],
  );

  const onToggleArchived = useCallback(() => {
    void updateSidebarState((current) => ({
      ...current,
      view: {
        ...current.view,
        show_archived: !current.view.show_archived,
      },
    }));
  }, [updateSidebarState]);

  const sidebarProps = useMemo(
    () => ({
      sessions,
      executions,
      activeExecutionKey: activeKey,
      loading,
      onNewExecution,
      onNewChat: onNewExecution,
      onSelect: onSelectExecution,
      onRequestDeleteExecution: onRequestDelete,
      onRequestDelete,
      onTogglePin,
      onRequestRename,
      onToggleArchive,
      onToggleGroup,
      onRequestRenameProject,
      onNewExecutionInProject,
      onNewChatInProject: onNewExecutionInProject,
      onOpenSettings,
      onOpenApps,
      onOpenAutomations,
      onOpenSkills,
      onSettingsIntent,
      onOpenSearch: onOpenSessionSearch,
      activeUtility:
        activeShellView === "apps" || activeShellView === "automations" || activeShellView === "skills"
          ? activeShellView
          : null,
      onToggleArchived,
      pinnedKeys: sidebarState.pinned_keys,
      archivedKeys: sidebarState.archived_keys,
      titleOverrides: sidebarState.title_overrides,
      projectNameOverrides: sidebarState.project_name_overrides,
      collapsedGroups: sidebarState.collapsed_groups,
      runningExecutionIds: runningExecutionIdList,
      updatedExecutionIds: updatedExecutionIdList,
      runningChatIds: runningExecutionIdList,
      updatedChatIds: updatedExecutionIdList,
      viewState: sidebarState.view,
      showArchived: sidebarState.view.show_archived,
      archivedCount: sidebarState.archived_keys.length,
      defaultWorkspacePath,
    }),
    [
      activeKey,
      activeShellView,
      defaultWorkspacePath,
      executions,
      loading,
      onNewExecution,
      onNewExecutionInProject,
      onOpenApps,
      onOpenAutomations,
      onOpenSessionSearch,
      onOpenSettings,
      onOpenSkills,
      onRequestDelete,
      onRequestRename,
      onRequestRenameProject,
      onSelectExecution,
      onSettingsIntent,
      onToggleArchive,
      onToggleArchived,
      onToggleGroup,
      onTogglePin,
      runningExecutionIdList,
      sessions,
      sidebarState,
      updatedExecutionIdList,
    ],
  );

  return {
    onSelectExecution,
    onTogglePin,
    onToggleGroup,
    onToggleArchived,
    sidebarProps,
  };
}
