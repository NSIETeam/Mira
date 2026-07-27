import { useCallback, useEffect, useRef, useState } from "react";

import {
  rememberRestartRoute,
  RESTART_ROUTE_KEY,
  RESTART_STARTED_KEY,
} from "@/shells/host";

interface RuntimeSessionSummary {
  chatId: string;
  runStartedAt?: number | null;
}

interface RuntimeClient {
  defaultExecutionId?: string | null;
  attachExecution: (chatId: string) => void;
  sendSystemCommand: (chatId: string, command: string) => Promise<unknown>;
  onRunStatus: (
    callback: (chatId: string, startedAt: number | null | undefined) => void,
  ) => () => void;
  onStatus: (callback: (status: string) => void) => () => void;
}

interface UseExecutionRuntimeStateOptions {
  client: RuntimeClient;
  loading: boolean;
  sessions: RuntimeSessionSummary[];
  activeSessionChatId: string | null;
  activeExecutionIdRef: React.MutableRefObject<string | null>;
  setUpdatedExecutionIds: React.Dispatch<React.SetStateAction<Set<string>>>;
  formatRestartCompleted: (seconds: string) => string;
}

export function useExecutionRuntimeState({
  client,
  loading,
  sessions,
  activeSessionChatId,
  activeExecutionIdRef,
  setUpdatedExecutionIds,
  formatRestartCompleted,
}: UseExecutionRuntimeStateOptions) {
  const restartSawDisconnectRef = useRef(false);
  const runningExecutionIdsRef = useRef<Set<string>>(new Set());
  const [restartToast, setRestartToast] = useState<string | null>(null);
  const [isRestarting, setIsRestarting] = useState(false);
  const [runningExecutionIds, setRunningExecutionIds] = useState<Set<string>>(
    () => new Set(),
  );

  useEffect(() => {
    if (loading) return;
    const activeRunIds = sessions
      .filter((session) => typeof session.runStartedAt === "number")
      .map((session) => session.chatId);
    if (activeRunIds.length === 0) return;

    for (const executionId of activeRunIds) {
      client.attachExecution(executionId);
    }
    setRunningExecutionIds((current) => {
      let changed = false;
      const next = new Set(current);
      for (const executionId of activeRunIds) {
        if (!next.has(executionId)) changed = true;
        next.add(executionId);
      }
      if (!changed) return current;
      runningExecutionIdsRef.current = next;
      return next;
    });
    setUpdatedExecutionIds((current) => {
      let changed = false;
      const next = new Set(current);
      for (const executionId of activeRunIds) {
        if (next.delete(executionId)) changed = true;
      }
      return changed ? next : current;
    });
  }, [client, loading, sessions, setUpdatedExecutionIds]);

  const onRestart = useCallback(() => {
    const executionId = activeSessionChatId ?? client.defaultExecutionId;
    if (!executionId) return;
    restartSawDisconnectRef.current = false;
    setIsRestarting(true);
    rememberRestartRoute();
    try {
      window.localStorage.setItem(RESTART_STARTED_KEY, String(Date.now()));
    } catch {
      // ignore storage errors
    }
    void client.sendSystemCommand(executionId, "/restart").catch(() => {});
  }, [activeSessionChatId, client]);

  useEffect(() => {
    return client.onRunStatus((chatId, startedAt) => {
      if (startedAt != null) {
        const nextRunning = new Set(runningExecutionIdsRef.current);
        nextRunning.add(chatId);
        runningExecutionIdsRef.current = nextRunning;
        setRunningExecutionIds(nextRunning);
        setUpdatedExecutionIds((current) => {
          if (!current.has(chatId)) return current;
          const next = new Set(current);
          next.delete(chatId);
          return next;
        });
        return;
      }

      if (!runningExecutionIdsRef.current.has(chatId)) return;
      const nextRunning = new Set(runningExecutionIdsRef.current);
      nextRunning.delete(chatId);
      runningExecutionIdsRef.current = nextRunning;
      setRunningExecutionIds(nextRunning);
      setUpdatedExecutionIds((current) => {
        const next = new Set(current);
        if (activeExecutionIdRef.current === chatId) {
          next.delete(chatId);
        } else {
          next.add(chatId);
        }
        return next;
      });
    });
  }, [activeExecutionIdRef, client, setUpdatedExecutionIds]);

  useEffect(() => {
    return client.onStatus((status) => {
      const startedAt = (() => {
        try {
          return Number(window.localStorage.getItem(RESTART_STARTED_KEY) ?? "0");
        } catch {
          return 0;
        }
      })();
      if (!startedAt) return;
      if (status !== "open") {
        restartSawDisconnectRef.current = true;
        return;
      }
      const elapsedMs = Date.now() - startedAt;
      if (!restartSawDisconnectRef.current && elapsedMs < 1500) return;
      try {
        window.localStorage.removeItem(RESTART_STARTED_KEY);
        window.localStorage.removeItem(RESTART_ROUTE_KEY);
      } catch {
        // ignore storage errors
      }
      setIsRestarting(false);
      setRestartToast(formatRestartCompleted((elapsedMs / 1000).toFixed(1)));
      window.setTimeout(() => setRestartToast(null), 3_500);
    });
  }, [client, formatRestartCompleted]);

  return {
    runningExecutionIds,
    isRestarting,
    restartToast,
    onRestart,
  };
}
