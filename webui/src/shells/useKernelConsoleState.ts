import { useEffect, useState } from "react";

import type { StreamError } from "@/lib/nanobot-client";

export interface KernelConsoleErrorEntry {
  id: string;
  kind: StreamError["kind"];
  message: string;
  at: number;
}

export function useKernelConsoleState(client: {
  onError: (handler: (error: StreamError) => void) => () => void;
  onStatus: (handler: (status: string) => void) => () => void;
  onRuntimeModelUpdate: (
    handler: (modelName: string | null, modelPreset?: string | null) => void,
  ) => () => void;
}) {
  const [connectionStatus, setConnectionStatus] = useState<string>("idle");
  const [runtimeModel, setRuntimeModel] = useState<string | null>(null);
  const [recentErrors, setRecentErrors] = useState<KernelConsoleErrorEntry[]>([]);

  useEffect(() => client.onStatus(setConnectionStatus), [client]);

  useEffect(() => {
    return client.onRuntimeModelUpdate((modelName, modelPreset) => {
      setRuntimeModel(modelPreset || modelName || null);
    });
  }, [client]);

  useEffect(() => {
    return client.onError((error) => {
      const message =
        error.kind === "workspace_scope_rejected"
          ? error.reason || "workspace scope rejected by gateway"
          : "message rejected by transport policy";
      const row: KernelConsoleErrorEntry = {
        id: `${Date.now()}-${error.kind}-${Math.random().toString(36).slice(2, 8)}`,
        kind: error.kind,
        message,
        at: Date.now(),
      };
      setRecentErrors((current) => [row, ...current].slice(0, 8));
    });
  }, [client]);

  return {
    connectionStatus,
    runtimeModel,
    recentErrors,
  };
}
