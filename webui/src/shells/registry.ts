import type { ComponentType } from "react";

import type { ShellDescriptorPayload } from "@/lib/types";

import { EngineeringShellLayout } from "./EngineeringShellLayout";
import { ReviewShellLayout } from "./ReviewShellLayout";
import { SingleExecutionShellLayout } from "./SingleExecutionShellLayout";
import type { ShellHostContract, ShellViewProps } from "./types";

export type ShellViewComponent = ComponentType<ShellViewProps>;
const HOST_CONTRACT_SCHEMA = "mira.host/v1";
const HOST_CONTRACT_VERSION = 1;
const KNOWN_SHELL_MODES = new Set<ShellHostContract["mode"]>([
  "engineering",
  "single-execution",
  "review",
]);
const DEFAULT_PRIVILEGE_CONTRACT: ShellHostContract["privilege"] = {
  role: "user",
  canElevate: false,
  elevationMode: "none",
  elevateHint: null,
  dropHint: null,
  sessionPolicy: "observe-only",
};

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
    allowPrivilegedRuntimeControls: true,
  },
  actions: {
    allowExecutionFork: true,
  },
  composer: {
    allowComposer: true,
    readOnlyExecution: false,
  },
  privilege: DEFAULT_PRIVILEGE_CONTRACT,
});

function buildUserShellContract({
  mode,
  chrome,
  surfaces,
  composer,
}: {
  mode: ShellHostContract["mode"];
  chrome: ShellHostContract["chrome"];
  surfaces: ShellHostContract["surfaces"];
  composer: ShellHostContract["composer"];
}): ShellHostContract {
  return buildHostContract({
    mode,
    chrome,
    surfaces,
    actions: {
      allowExecutionFork: false,
    },
    composer,
    privilege: DEFAULT_PRIVILEGE_CONTRACT,
  });
}

function readBooleanOr(primary: unknown, fallback: boolean): boolean {
  return typeof primary === "boolean" ? primary : fallback;
}

function readFiniteNumberOr(primary: unknown, fallback: number): number {
  return typeof primary === "number" && Number.isFinite(primary) ? primary : fallback;
}

function readNonEmptyStringOr(primary: unknown, fallback: string): string {
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
  const schema = readNonEmptyStringOr(raw.schema, fallback.schema);
  const version = readFiniteNumberOr(raw.version, fallback.version);
  const showSidebarChrome = readBooleanOr(
    rawChrome?.showSidebarChrome,
    fallback.chrome.showSidebarChrome,
  );
  const showSearchDialog = readBooleanOr(
    rawChrome?.showSearchDialog,
    fallback.chrome.showSearchDialog,
  );
  const allowUtilitySurface = readBooleanOr(
    rawSurfaces?.allowUtilitySurface,
    fallback.surfaces.allowUtilitySurface,
  );
  const allowExecutionFork = readBooleanOr(
    rawActions?.allowExecutionFork,
    fallback.actions.allowExecutionFork,
  );
  const allowWorkspaceControls = readBooleanOr(
    rawSurfaces?.allowWorkspaceControls,
    fallback.surfaces.allowWorkspaceControls,
  );
  const allowRuntimeModelControls = readBooleanOr(
    rawSurfaces?.allowRuntimeModelControls,
    fallback.surfaces.allowRuntimeModelControls,
  );
  const allowKernelConsole = readBooleanOr(
    rawSurfaces?.allowKernelConsole,
    fallback.surfaces.allowKernelConsole,
  );
  const allowPrivilegedRuntimeControls = readBooleanOr(
    rawSurfaces?.allowPrivilegedRuntimeControls,
    fallback.surfaces.allowPrivilegedRuntimeControls,
  );
  const allowComposer = readBooleanOr(
    rawComposer?.allowComposer,
    fallback.composer.allowComposer,
  );
  const readOnlyExecution = readBooleanOr(
    rawComposer?.readOnlyExecution,
    fallback.composer.readOnlyExecution,
  );
  const privilegeRole = readNonEmptyStringOr(
    typeof raw.privilege?.role === "string" ? raw.privilege.role : undefined,
    fallback.privilege.role,
  );
  const privilegeCanElevate = readBooleanOr(
    raw.privilege?.canElevate,
    fallback.privilege.canElevate,
  );
  const privilegeElevationMode = readNonEmptyStringOr(
    typeof raw.privilege?.elevationMode === "string" ? raw.privilege.elevationMode : undefined,
    fallback.privilege.elevationMode ?? "none",
  );
  const privilegeElevateHint =
    typeof raw.privilege?.elevateHint === "string" && raw.privilege.elevateHint.trim()
      ? raw.privilege.elevateHint
      : (fallback.privilege.elevateHint ?? null);
  const privilegeDropHint =
    typeof raw.privilege?.dropHint === "string" && raw.privilege.dropHint.trim()
      ? raw.privilege.dropHint
      : (fallback.privilege.dropHint ?? null);
  const privilegeSessionPolicy = readNonEmptyStringOr(
    typeof raw.privilege?.sessionPolicy === "string" ? raw.privilege.sessionPolicy : undefined,
    fallback.privilege.sessionPolicy ?? "observe-only",
  );
  const contract = buildHostContract({
    mode: KNOWN_SHELL_MODES.has(raw.mode as ShellHostContract["mode"])
      ? raw.mode as ShellHostContract["mode"]
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
      allowPrivilegedRuntimeControls,
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
      elevationMode: privilegeElevationMode,
      elevateHint: privilegeElevateHint,
      dropHint: privilegeDropHint,
      sessionPolicy: privilegeSessionPolicy,
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
    hostContract: buildUserShellContract({
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
        allowPrivilegedRuntimeControls: true,
      },
      composer: {
        allowComposer: true,
        readOnlyExecution: false,
      },
    }),
  },
  review: {
    component: ReviewShellLayout,
    hostContract: buildUserShellContract({
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
        allowPrivilegedRuntimeControls: false,
      },
      composer: {
        allowComposer: false,
        readOnlyExecution: true,
      },
    }),
  },
};

function shellRegistryKey(
  shellDescriptor: ShellDescriptorPayload | null | undefined,
): string {
  const contractMode = shellDescriptor?.host_contract?.mode;
  if (KNOWN_SHELL_MODES.has(contractMode as ShellHostContract["mode"])) {
    return contractMode as ShellHostContract["mode"];
  }
  return shellDescriptor?.name?.trim() ?? "";
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
