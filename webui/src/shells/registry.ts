import type { ComponentType } from "react";

import type { ShellDescriptorPayload } from "@/lib/types";

import { EngineeringShellLayout } from "./EngineeringShellLayout";
import { ReviewShellLayout } from "./ReviewShellLayout";
import { SingleExecutionShellLayout } from "./SingleExecutionShellLayout";
import type { ShellHostContract, ShellViewProps } from "./types";

export type ShellViewComponent = ComponentType<ShellViewProps>;

export interface ShellViewRegistration {
  component: ShellViewComponent;
  hostContract: ShellHostContract;
}

function buildHostContract({
  mode,
  showSidebarChrome,
  showSearchDialog,
  allowUtilitySurface,
  allowExecutionFork,
  allowWorkspaceControls,
  allowRuntimeModelControls,
  allowKernelConsole,
  allowComposer,
  readOnlyExecution,
}: {
  mode: ShellHostContract["mode"];
  showSidebarChrome: boolean;
  showSearchDialog: boolean;
  allowUtilitySurface: boolean;
  allowExecutionFork: boolean;
  allowWorkspaceControls: boolean;
  allowRuntimeModelControls: boolean;
  allowKernelConsole: boolean;
  allowComposer: boolean;
  readOnlyExecution: boolean;
}): ShellHostContract {
  return {
    mode,
    showSidebarChrome,
    showSearchDialog,
    allowUtilitySurface,
    allowExecutionFork,
    allowWorkspaceControls,
    allowRuntimeModelControls,
    allowKernelConsole,
    allowComposer,
    readOnlyExecution,
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
  };
}

const DEFAULT_HOST_CONTRACT = buildHostContract({
  mode: "engineering",
  showSidebarChrome: true,
  showSearchDialog: true,
  allowUtilitySurface: true,
  allowExecutionFork: true,
  allowWorkspaceControls: true,
  allowRuntimeModelControls: true,
  allowKernelConsole: true,
  allowComposer: true,
  readOnlyExecution: false,
});

function readCompatBoolean(
  primary: unknown,
  grouped: unknown,
  fallback: boolean,
): boolean {
  if (typeof primary === "boolean") return primary;
  if (typeof grouped === "boolean") return grouped;
  return fallback;
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
  const showSidebarChrome = readCompatBoolean(
    raw.showSidebarChrome,
    rawChrome?.showSidebarChrome,
    fallback.showSidebarChrome,
  );
  const showSearchDialog = readCompatBoolean(
    raw.showSearchDialog,
    rawChrome?.showSearchDialog,
    fallback.showSearchDialog,
  );
  const allowUtilitySurface = readCompatBoolean(
    raw.allowUtilitySurface,
    rawSurfaces?.allowUtilitySurface,
    fallback.allowUtilitySurface,
  );
  const allowExecutionFork = readCompatBoolean(
    raw.allowExecutionFork,
    rawActions?.allowExecutionFork,
    fallback.allowExecutionFork,
  );
  const allowWorkspaceControls = readCompatBoolean(
    raw.allowWorkspaceControls,
    rawSurfaces?.allowWorkspaceControls,
    fallback.allowWorkspaceControls,
  );
  const allowRuntimeModelControls = readCompatBoolean(
    raw.allowRuntimeModelControls,
    rawSurfaces?.allowRuntimeModelControls,
    fallback.allowRuntimeModelControls,
  );
  const allowKernelConsole = readCompatBoolean(
    raw.allowKernelConsole,
    rawSurfaces?.allowKernelConsole,
    fallback.allowKernelConsole,
  );
  const allowComposer = readCompatBoolean(
    raw.allowComposer,
    rawComposer?.allowComposer,
    fallback.allowComposer,
  );
  const readOnlyExecution = readCompatBoolean(
    raw.readOnlyExecution,
    rawComposer?.readOnlyExecution,
    fallback.readOnlyExecution,
  );
  return buildHostContract({
    mode:
      raw.mode === "single-execution" || raw.mode === "review" || raw.mode === "engineering"
        ? raw.mode
        : fallback.mode,
    showSidebarChrome,
    showSearchDialog,
    allowUtilitySurface,
    allowExecutionFork,
    allowWorkspaceControls,
    allowRuntimeModelControls,
    allowKernelConsole,
    allowComposer,
    readOnlyExecution,
  });
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
      showSidebarChrome: false,
      showSearchDialog: false,
      allowUtilitySurface: false,
      allowExecutionFork: false,
      allowWorkspaceControls: false,
      allowRuntimeModelControls: false,
      allowKernelConsole: true,
      allowComposer: true,
      readOnlyExecution: false,
    }),
  },
  review: {
    component: ReviewShellLayout,
    hostContract: buildHostContract({
      mode: "review",
      showSidebarChrome: false,
      showSearchDialog: false,
      allowUtilitySurface: true,
      allowExecutionFork: false,
      allowWorkspaceControls: false,
      allowRuntimeModelControls: false,
      allowKernelConsole: true,
      allowComposer: false,
      readOnlyExecution: true,
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
