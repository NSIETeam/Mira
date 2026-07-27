import { createContext, useContext, type ReactNode } from "react";

import type { miraClient } from "@/lib/mira-client";
import type { WebUIIngressLimits } from "@/lib/types";

interface ClientContextValue {
  client: miraClient;
  token: string;
  modelName: string | null;
  ingressLimits: WebUIIngressLimits | null;
}

const ClientContext = createContext<ClientContextValue | null>(null);

export function ClientProvider({
  client,
  token,
  modelName = null,
  ingressLimits = null,
  children,
}: {
  client: miraClient;
  token: string;
  modelName?: string | null;
  ingressLimits?: WebUIIngressLimits | null;
  children: ReactNode;
}) {
  return (
    <ClientContext.Provider value={{ client, token, modelName, ingressLimits }}>
      {children}
    </ClientContext.Provider>
  );
}

export function useClient(): ClientContextValue {
  const ctx = useContext(ClientContext);
  if (!ctx) {
    throw new Error("useClient must be used within a ClientProvider");
  }
  return ctx;
}
