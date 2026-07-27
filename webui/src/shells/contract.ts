import type { ShellHostContract } from "./types";
import type { ShellDescriptorPayload } from "@/lib/types";

export function shellChromeContract(contract: ShellHostContract) {
  return contract.chrome;
}

export function shellSurfaceContract(contract: ShellHostContract) {
  return contract.surfaces;
}

export function shellActionContract(contract: ShellHostContract) {
  return contract.actions;
}

export function shellComposerContract(contract: ShellHostContract) {
  return contract.composer;
}

export function shellShowsSidebarChrome(contract: ShellHostContract): boolean {
  return shellChromeContract(contract).showSidebarChrome;
}

export function shellShowsSearchDialog(contract: ShellHostContract): boolean {
  return shellChromeContract(contract).showSearchDialog;
}

export function shellAllowsUtilitySurface(contract: ShellHostContract): boolean {
  return shellSurfaceContract(contract).allowUtilitySurface;
}

export function shellAllowsWorkspaceControls(contract: ShellHostContract): boolean {
  return shellSurfaceContract(contract).allowWorkspaceControls;
}

export function shellAllowsRuntimeModelControls(contract: ShellHostContract): boolean {
  return shellSurfaceContract(contract).allowRuntimeModelControls;
}

export function shellAllowsKernelConsole(contract: ShellHostContract): boolean {
  return shellSurfaceContract(contract).allowKernelConsole;
}

export function shellAllowsExecutionFork(contract: ShellHostContract): boolean {
  return shellActionContract(contract).allowExecutionFork;
}

export function shellAllowsComposer(contract: ShellHostContract): boolean {
  return shellComposerContract(contract).allowComposer;
}

export function shellReadOnlyExecution(contract: ShellHostContract): boolean {
  return shellComposerContract(contract).readOnlyExecution;
}

export function shellDataAttributes({
  shellDescriptor,
  shellSupportsThreads,
  shellSupportsRuntimeControls,
  shellSupportsFileActivity,
  hostContract,
  fallbackName,
  fallbackTheme,
  layout,
}: {
  shellDescriptor: ShellDescriptorPayload | null;
  shellSupportsThreads: boolean;
  shellSupportsRuntimeControls: boolean;
  shellSupportsFileActivity: boolean;
  hostContract: ShellHostContract;
  fallbackName: string;
  fallbackTheme: string;
  layout?: string;
}): Record<string, string> {
  return {
    "data-shell-name": shellDescriptor?.name ?? fallbackName,
    "data-shell-theme": shellDescriptor?.theme ?? fallbackTheme,
    "data-shell-description": shellDescriptor?.description ?? "",
    "data-shell-supports-threads": shellSupportsThreads ? "true" : "false",
    "data-shell-supports-runtime-controls": shellSupportsRuntimeControls ? "true" : "false",
    "data-shell-supports-file-activity": shellSupportsFileActivity ? "true" : "false",
    ...(layout ? { "data-shell-layout": layout } : {}),
    "data-shell-mode": hostContract.mode,
    "data-shell-read-only": shellReadOnlyExecution(hostContract) ? "true" : "false",
  };
}
