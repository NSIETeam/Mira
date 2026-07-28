import type { ComponentType } from "react";

import type { ShellDescriptorPayload } from "@/lib/types";

import { EngineeringShellLayout } from "./EngineeringShellLayout";
import { ReviewShellLayout } from "./ReviewShellLayout";
import { SingleExecutionShellLayout } from "./SingleExecutionShellLayout";
import type { ShellHostContract, ShellViewProps } from "./types";

export type ShellViewComponent = ComponentType<ShellViewProps>;
const HOST_CONTRACT_SCHEMA = "mira.host/v1";
const HOST_CONTRACT_VERSION = 1;

export interface ShellViewRegistration {
  component: ShellViewComponent;
  hostContract: ShellHostContract;
}

function buildHostContract({
  mode,
  chrome,
  surfaces,
  actions,
  composer,
  privilege,
}: {
  mode: ShellHostContract["mode"];
  chrome: ShellHostContract["chrome"];
  surfaces: ShellHostContract["surfaces"];
  actions: ShellHostContract["actions"];
  composer: ShellHostContract["composer"];
  privilege: ShellHostContract["privilege"];
}): ShellHostContract {
  return {
    schema: HOST_CONTRACT_SCHEMA,
    version: HOST_CONTRACT_VERSION,
    mode,
    chrome,
    surfaces,
    actions,
    composer,
    privilege,
  };
}

const DEFAULT_HOST_CONTRACT = buildHostContract({
  mode: "engineering",
  chrome: {
    showSidebarChrome: true,
    showSearchDialog: true,
  },
  surfaces: {
    allowUtilitySurface: true,
    allowWorkspaceControls: true,
    allowRuntimeModelControls: true,
    allowKernelConsole: true,
  },
  actions: {
    allowExecutionFork: true,
  },
  composer: {
    allowComposer: true,
    readOnlyExecution: false,
  },
  privilege: {
    role: "user",
    canElevate: false,
  },
});

function readCompatBoolean(
  grouped: unknown,
  fallback: boolean,
): boolean {
  if (typeof grouped === "boolean") return grouped;
  return fallback;
}

function readCompatNumber(primary: unknown, fallback: number): number {
  return typeof primary === "number" && Number.isFinite(primary) ? primary : fallback;
}

function readCompatString(primary: unknown, fallback: string): string {
  return typeof primary === "string" && primary.trim() ? primary : fallback;
}

function coerceHostContract(
  shellDescriptor: ShellDescriptorPayload | null | undefined,
  fallback: ShellHostContract,
): ShellHostContract {
  const raw = shellDescriptor?.host_contract;
  if (!raw || typeof raw !== "object") return fallback;
  const rawChrome = raw.chrome;
  const rawSurfaces = raw.surfaces;
  const rawActions = raw.actions;
  const rawComposer = raw.composer;
  const schema = readCompatString(raw.schema, fallback.schema);
  const version = readCompatNumber(raw.version, fallback.version);
  const showSidebarChrome = readCompatBoolean(
    rawChrome?.showSidebarChrome,
    fallback.chrome.showSidebarChrome,
  );
  const showSearchDialog = readCompatBoolean(
    rawChrome?.showSearchDialog,
    fallback.chrome.showSearchDialog,
  );
  const allowUtilitySurface = readCompatBoolean(
    rawSurfaces?.allowUtilitySurface,
    fallback.surfaces.allowUtilitySurface,
  );
  const allowExecutionFork = readCompatBoolean(
    rawActions?.allowExecutionFork,
    fallback.actions.allowExecutionFork,
  );
  const allowWorkspaceControls = readCompatBoolean(
    rawSurfaces?.allowWorkspaceControls,
    fallback.surfaces.allowWorkspaceControls,
  );
  const allowRuntimeModelControls = readCompatBoolean(
    rawSurfaces?.allowRuntimeModelControls,
    fallback.surfaces.allowRuntimeModelControls,
  );
  const allowKernelConsole = readCompatBoolean(
    rawSurfaces?.allowKernelConsole,
    fallback.surfaces.allowKernelConsole,
  );
  const allowComposer = readCompatBoolean(
    rawComposer?.allowComposer,
    fallback.composer.allowComposer,
  );
  const readOnlyExecution = readCompatBoolean(
    rawComposer?.readOnlyExecution,
    fallback.composer.readOnlyExecution,
  );
  const privilegeRole = readCompatString(
    typeof raw.privilege?.role === "string" ? raw.privilege.role : undefined,
    fallback.privilege.role,
  );
  const privilegeCanElevate = readCompatBoolean(
    raw.privilege?.canElevate,
    fallback.privilege.canElevate,
  );
  const contract = buildHostContract({
    mode:
      raw.mode === "single-execution" || raw.mode === "review" || raw.mode === "engineering"
        ? raw.mode
        : fallback.mode,
    chrome: {
      showSidebarChrome,
      showSearchDialog,
    },
    surfaces: {
      allowUtilitySurface,
      allowWorkspaceControls,
      allowRuntimeModelControls,
      allowKernelConsole,
    },
    actions: {
      allowExecutionFork,
    },
    composer: {
      allowComposer,
      readOnlyExecution,
    },
    privilege: {
      role: privilegeRole,
      canElevate: privilegeCanElevate,
    },
  });
  return {
    ...contract,
    schema,
    version,
  };
}

const SHELL_VIEW_REGISTRY: Record<string, ShellViewRegistration> = {
  engineering: {
    component: EngineeringShellLayout,
    hostContract: DEFAULT_HOST_CONTRACT,
  },
  "single-execution": {
    component: SingleExecutionShellLayout,
    hostContract: buildHostContract({
      mode: "single-execution",
      chrome: {
        showSidebarChrome: false,
        showSearchDialog: false,
      },
      surfaces: {
        allowUtilitySurface: false,
        allowWorkspaceControls: false,
        allowRuntimeModelControls: false,
        allowKernelConsole: true,
      },
      actions: {
        allowExecutionFork: false,
      },
      composer: {
        allowComposer: true,
        readOnlyExecution: false,
      },
      privilege: {
        role: "user",
        canElevate: false,
      },
    }),
  },
  review: {
    component: ReviewShellLayout,
    hostContract: buildHostContract({
      mode: "review",
      chrome: {
        showSidebarChrome: false,
        showSearchDialog: false,
      },
      surfaces: {
        allowUtilitySurface: true,
        allowWorkspaceControls: false,
        allowRuntimeModelControls: false,
        allowKernelConsole: true,
      },
      actions: {
        allowExecutionFork: false,
      },
      composer: {
        allowComposer: false,
        readOnlyExecution: true,
      },
      privilege: {
        role: "user",
        canElevate: false,
      },
    }),
  },
};

function shellRegistryKey(
  shellDescriptor: ShellDescriptorPayload | null | undefined,
): string {
  const contractMode = shellDescriptor?.host_contract?.mode;
  if (
    contractMode === "engineering"
    || contractMode === "single-execution"
    || contractMode === "review"
  ) {
    return contractMode;
  }
  const shellName = shellDescriptor?.name?.trim() ?? "";
  if (shellName === "single-execution-shell") return "single-execution";
  if (shellName === "review-shell") return "review";
  if (shellName === "engineering-shell" || shellName === "mira-shell") {
    return "engineering";
  }
  return shellName;
}

export function resolveShellRegistration(
  shellDescriptor: ShellDescriptorPayload | null | undefined,
): ShellViewRegistration {
  const registryName = shellRegistryKey(shellDescriptor);
  const fallbackRegistration = SHELL_VIEW_REGISTRY[registryName] ?? {
    component: EngineeringShellLayout,
    hostContract: DEFAULT_HOST_CONTRACT,
  };
  return {
    component: fallbackRegistration.component,
    hostContract: coerceHostContract(shellDescriptor, fallbackRegistration.hostContract),
  };
}
