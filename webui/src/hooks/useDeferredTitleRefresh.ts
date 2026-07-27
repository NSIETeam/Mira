import { useCallback, useEffect, useRef } from "react";

import type { ExecutionSummary } from "@/lib/types";

const TITLE_REFRESH_RETRY_DELAYS_MS = [1_000, 3_000, 7_000] as const;

function hasGeneratedTitle(execution: ExecutionSummary | null): boolean {
  return !!execution?.title?.trim();
}

/**
 * The server generates WebUI titles after the main turn has already ended.
 * Refresh once immediately, then retry lightly for untitled sessions so the
 * async title appears even if the websocket metadata notification is delayed.
 */
export function useDeferredTitleRefresh(
  activeExecution: ExecutionSummary | null,
  refresh: () => Promise<void>,
  retryDelaysMs: readonly number[] = TITLE_REFRESH_RETRY_DELAYS_MS,
): () => void {
  const activeExecutionRef = useRef(activeExecution);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  activeExecutionRef.current = activeExecution;

  const clearTimers = useCallback(() => {
    for (const timer of timersRef.current) {
      clearTimeout(timer);
    }
    timersRef.current = [];
  }, []);

  useEffect(() => clearTimers, [clearTimers]);

  useEffect(() => {
    clearTimers();
  }, [activeExecution?.key, clearTimers]);

  useEffect(() => {
    if (hasGeneratedTitle(activeExecution)) {
      clearTimers();
    }
  }, [activeExecution, clearTimers]);

  return useCallback(() => {
    void refresh();

    const executionAtTurnEnd = activeExecutionRef.current;
    if (!executionAtTurnEnd || hasGeneratedTitle(executionAtTurnEnd)) {
      return;
    }

    clearTimers();
    for (const delayMs of retryDelaysMs) {
      const timer = setTimeout(() => {
        const latest = activeExecutionRef.current;
        if (
          !latest ||
          latest.key !== executionAtTurnEnd.key ||
          hasGeneratedTitle(latest)
        ) {
          return;
        }
        void refresh();
      }, delayMs);
      timersRef.current.push(timer);
    }
  }, [clearTimers, refresh, retryDelaysMs]);
}
