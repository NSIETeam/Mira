import { useEffect } from "react";

import { defaultShellRoute, readShellRoute, type ShellRoute } from "@/shells/host";
import type { ExecutionSummary, WorkspaceScopePayload } from "@/lib/types";

interface SessionUpdateClient {
  onSessionUpdate: (
    callback: (
      chatId: string,
      scope?: string,
      workspaceScope?: WorkspaceScopePayload | null,
    ) => void,
  ) => () => void;
}

interface UseExecutionSessionStateOptions {
  client: SessionUpdateClient;
  loading: boolean;
  activeKey: string | null;
  activeExecutionId: string | null;
  activeExecutionIdRef: React.MutableRefObject<string | null>;
  sessions: ExecutionSummary[];
  executionSummaries: ExecutionSummary[];
  navigate: (route: ShellRoute, options?: { replace?: boolean }) => void;
  setUpdatedExecutionIds: React.Dispatch<React.SetStateAction<Set<string>>>;
  setWorkspaceOverrides: React.Dispatch<
    React.SetStateAction<Record<string, WorkspaceScopePayload>>
  >;
  setDraftWorkspaceScope: React.Dispatch<
    React.SetStateAction<WorkspaceScopePayload | null>
  >;
  setWorkspaceError: React.Dispatch<React.SetStateAction<string | null>>;
  normalizeWorkspaceScope: (scope: WorkspaceScopePayload) => WorkspaceScopePayload;
  refreshWorkspaces: () => Promise<void>;
}

export function useExecutionSessionState({
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
}: UseExecutionSessionStateOptions) {
  useEffect(() => {
    activeExecutionIdRef.current = activeExecutionId;
    if (!activeExecutionId) return;
    setUpdatedExecutionIds((current) => {
      if (!current.has(activeExecutionId)) return current;
      const next = new Set(current);
      next.delete(activeExecutionId);
      return next;
    });
  }, [activeExecutionId, activeExecutionIdRef, setUpdatedExecutionIds]);

  useEffect(() => {
    if (loading) return;
    const knownExecutionIds = new Set(
      executionSummaries.map((session) => session.chatId),
    );
    setUpdatedExecutionIds((current) => {
      const next = new Set(
        Array.from(current).filter((chatId) => knownExecutionIds.has(chatId)),
      );
      return next.size === current.size ? current : next;
    });
    setWorkspaceOverrides((current) => {
      const entries = Object.entries(current).filter(([chatId]) =>
        knownExecutionIds.has(chatId),
      );
      return entries.length === Object.keys(current).length
        ? current
        : Object.fromEntries(entries);
    });
  }, [
    executionSummaries,
    loading,
    setUpdatedExecutionIds,
    setWorkspaceOverrides,
  ]);

  useEffect(() => {
    if (loading || !activeKey) return;
    if (sessions.some((session) => session.key === activeKey)) return;
    const currentRoute = readShellRoute();
    navigate(
      currentRoute.view === "chat"
        ? defaultShellRoute()
        : {
            ...currentRoute,
            activeKey: null,
          },
      { replace: true },
    );
  }, [activeKey, loading, navigate, sessions]);

  useEffect(() => {
    return client.onSessionUpdate((chatId, scope, workspaceScope) => {
      if (scope === "thread") {
        setUpdatedExecutionIds((current) => {
          const next = new Set(current);
          if (activeExecutionIdRef.current === chatId) {
            next.delete(chatId);
          } else {
            next.add(chatId);
          }
          return next.size === current.size && next.has(chatId) === current.has(chatId)
            ? current
            : next;
        });
      }
      if (!workspaceScope) return;
      const next = normalizeWorkspaceScope(workspaceScope);
      setWorkspaceOverrides((current) => ({
        ...current,
        [chatId]: next,
      }));
      setDraftWorkspaceScope(next);
      setWorkspaceError(null);
      void refreshWorkspaces();
    });
  }, [
    activeExecutionIdRef,
    client,
    normalizeWorkspaceScope,
    refreshWorkspaces,
    setDraftWorkspaceScope,
    setUpdatedExecutionIds,
    setWorkspaceError,
    setWorkspaceOverrides,
  ]);
}
