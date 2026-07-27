import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchPairingRequests, runPairingAction } from "@/lib/api";
import type { ExecutionSummary, PairingRequestInfo, SessionAutomationJob } from "@/lib/types";
import type { ShellRoute } from "@/shells/host";

const PAIRING_POLL_INTERVAL_MS = 5_000;
const PAIRING_IDLE_POLL_INTERVAL_MS = 15_000;
const PAIRING_DISMISS_SNOOZE_MS = 30_000;

interface PendingDeleteState {
  key: string;
  label: string;
  automations?: SessionAutomationJob[];
}

interface PendingRenameState {
  key: string;
  label: string;
}

interface UseEngineeringOverlayStateOptions {
  token: string;
  pageVisible: boolean;
  activeKey: string | null;
  sessions: ExecutionSummary[];
  archivedKeys: string[];
  updateSidebarState: (updater: (current: any) => any) => Promise<any> | void;
  navigate: (route: ShellRoute, options?: { replace?: boolean }) => void;
  getExecutionAutomations: (key: string) => Promise<SessionAutomationJob[]>;
  deleteExecution: (
    key: string,
    options?: { deleteAutomations?: boolean },
  ) => Promise<{ blocked_by_automations?: boolean; automations?: SessionAutomationJob[] }>;
}

export function useEngineeringOverlayState({
  token,
  pageVisible,
  activeKey,
  sessions,
  archivedKeys,
  updateSidebarState,
  navigate,
  getExecutionAutomations,
  deleteExecution,
}: UseEngineeringOverlayStateOptions) {
  const [pendingDelete, setPendingDelete] = useState<PendingDeleteState | null>(null);
  const [pendingRename, setPendingRename] = useState<PendingRenameState | null>(null);
  const [pendingProjectRename, setPendingProjectRename] = useState<PendingRenameState | null>(null);
  const [pairingRequests, setPairingRequests] = useState<PairingRequestInfo[]>([]);
  const [pairingBusyCode, setPairingBusyCode] = useState<string | null>(null);
  const [pairingError, setPairingError] = useState<string | null>(null);
  const [snoozedPairingCodes, setSnoozedPairingCodes] = useState<Map<string, number>>(
    () => new Map(),
  );

  const refreshPairingRequests = useCallback(async (): Promise<number> => {
    try {
      const payload = await fetchPairingRequests(token);
      const requests = Array.isArray(payload.requests) ? payload.requests : [];
      setPairingRequests(requests);
      setSnoozedPairingCodes((current) => {
        if (current.size === 0) return current;
        const activeCodes = new Set(requests.map((request) => request.code));
        const now = Date.now();
        const next = new Map(
          Array.from(current).filter(
            ([code, snoozedUntil]) => activeCodes.has(code) && snoozedUntil > now,
          ),
        );
        return next.size === current.size ? current : next;
      });
      return requests.length;
    } catch {
      return 0;
    }
  }, [token]);

  useEffect(() => {
    if (!pageVisible) return undefined;

    let disposed = false;
    let timer: number | null = null;
    const poll = async () => {
      const requestCount = await refreshPairingRequests();
      if (disposed) return;
      timer = window.setTimeout(
        () => void poll(),
        requestCount > 0 ? PAIRING_POLL_INTERVAL_MS : PAIRING_IDLE_POLL_INTERVAL_MS,
      );
    };
    void poll();
    return () => {
      disposed = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [pageVisible, refreshPairingRequests]);

  const onRequestRename = useCallback((key: string, label: string) => {
    setPendingRename({ key, label });
  }, []);

  const onConfirmRename = useCallback(
    (title: string) => {
      if (!pendingRename) return;
      const key = pendingRename.key;
      setPendingRename(null);
      void updateSidebarState((current) => {
        const titleOverrides = { ...current.title_overrides };
        const cleaned = title.trim();
        if (cleaned) {
          titleOverrides[key] = cleaned;
        } else {
          delete titleOverrides[key];
        }
        return {
          ...current,
          title_overrides: titleOverrides,
        };
      });
    },
    [pendingRename, updateSidebarState],
  );

  const onRequestRenameProject = useCallback((key: string, label: string) => {
    setPendingProjectRename({ key, label });
  }, []);

  const onConfirmProjectRename = useCallback(
    (title: string) => {
      if (!pendingProjectRename) return;
      const key = pendingProjectRename.key;
      setPendingProjectRename(null);
      void updateSidebarState((current) => {
        const projectNameOverrides = { ...current.project_name_overrides };
        const cleaned = title.trim();
        if (cleaned) {
          projectNameOverrides[key] = cleaned;
        } else {
          delete projectNameOverrides[key];
        }
        return {
          ...current,
          project_name_overrides: projectNameOverrides,
        };
      });
    },
    [pendingProjectRename, updateSidebarState],
  );

  const onConfirmDelete = useCallback(async () => {
    if (!pendingDelete) return;
    const key = pendingDelete.key;
    const hasAutomations = (pendingDelete.automations?.length ?? 0) > 0;
    const deletingActive = activeKey === key;
    const currentIndex = sessions.findIndex((session) => session.key === key);
    const fallbackKey = deletingActive
      ? (sessions[currentIndex + 1]?.key ?? sessions[currentIndex - 1]?.key ?? null)
      : activeKey;
    try {
      const result = await deleteExecution(
        key,
        hasAutomations ? { deleteAutomations: true } : undefined,
      );
      if (result.blocked_by_automations) {
        setPendingDelete({
          ...pendingDelete,
          automations: result.automations ?? [],
        });
        return;
      }
      setPendingDelete(null);
      if (deletingActive) {
        navigate({
          view: "chat",
          activeKey: fallbackKey,
          settingsSection: "overview",
        }, { replace: true });
      }
    } catch (error) {
      console.error("Failed to delete session", error);
    }
  }, [activeKey, deleteExecution, navigate, pendingDelete, sessions]);

  const onRequestDelete = useCallback(async (key: string, label: string) => {
    let automations: SessionAutomationJob[] = [];
    try {
      automations = await getExecutionAutomations(key);
    } catch {
      // Backend still blocks destructive deletion when automations exist.
    }
    setPendingDelete({ key, label, automations });
  }, [getExecutionAutomations]);

  const visiblePairingRequests = useMemo(() => {
    const now = Date.now();
    return pairingRequests.filter((request) => {
      const snoozedUntil = snoozedPairingCodes.get(request.code);
      return !snoozedUntil || snoozedUntil <= now;
    });
  }, [pairingRequests, snoozedPairingCodes]);

  const onPairingAction = useCallback(
    async (action: "approve" | "deny", code: string) => {
      setPairingBusyCode(code);
      setPairingError(null);
      try {
        const payload = await runPairingAction(token, action, code);
        setPairingRequests(Array.isArray(payload.requests) ? payload.requests : []);
        setSnoozedPairingCodes((current) => {
          if (!current.has(code)) return current;
          const next = new Map(current);
          next.delete(code);
          return next;
        });
      } catch (error) {
        setPairingError((error as Error).message);
        void refreshPairingRequests();
      } finally {
        setPairingBusyCode(null);
      }
    },
    [refreshPairingRequests, token],
  );

  const onDismissPairingRequest = useCallback((code: string) => {
    setSnoozedPairingCodes((current) => {
      const snoozedUntil = Date.now() + PAIRING_DISMISS_SNOOZE_MS;
      if (current.get(code) === snoozedUntil) return current;
      const next = new Map(current);
      next.set(code, snoozedUntil);
      return next;
    });
  }, []);

  const onToggleArchive = useCallback(
    (key: string) => {
      void updateSidebarState((current) => {
        const archived = new Set(current.archived_keys);
        const pinned = current.pinned_keys.filter((item: string) => item !== key);
        if (archived.has(key)) {
          archived.delete(key);
        } else {
          archived.add(key);
        }
        return {
          ...current,
          pinned_keys: pinned,
          archived_keys: Array.from(archived),
        };
      });
      if (activeKey === key && !archivedKeys.includes(key)) {
        const archived = new Set([...archivedKeys, key]);
        const next = sessions.find((session) => !archived.has(session.key));
        navigate({
          view: "chat",
          activeKey: next?.key ?? null,
          settingsSection: "overview",
        });
      }
    },
    [activeKey, archivedKeys, navigate, sessions, updateSidebarState],
  );

  return {
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
  };
}
