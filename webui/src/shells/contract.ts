import type { ShellHostContract } from "./types";
import { resolveShellRegistration } from "./registry";
import type { ShellDescriptorPayload } from "@/lib/types";

export function normalizedShellHostContract(
  shellDescriptor: ShellDescriptorPayload | null,
): ShellHostContract {
  return resolveShellRegistration(shellDescriptor).hostContract;
}

export function normalizedShellMode(
  shellDescriptor: ShellDescriptorPayload | null,
): ShellHostContract["mode"] {
  return normalizedShellHostContract(shellDescriptor).mode;
}

export function shellDescriptorAllowsKernelConsole(
  shellDescriptor: ShellDescriptorPayload | null,
): boolean {
  return shellAllowsKernelConsole(normalizedShellHostContract(shellDescriptor));
}

export function shellShowsSidebarChrome(contract: ShellHostContract): boolean {
  return contract.chrome.showSidebarChrome;
}

export function shellShowsSearchDialog(contract: ShellHostContract): boolean {
  return contract.chrome.showSearchDialog;
}

export function shellAllowsUtilitySurface(contract: ShellHostContract): boolean {
  return contract.surfaces.allowUtilitySurface;
}

export function shellAllowsWorkspaceControls(contract: ShellHostContract): boolean {
  return contract.surfaces.allowWorkspaceControls;
}

export function shellAllowsRuntimeModelControls(contract: ShellHostContract): boolean {
  return contract.surfaces.allowRuntimeModelControls;
}

export function shellAllowsKernelConsole(contract: ShellHostContract): boolean {
  return contract.surfaces.allowKernelConsole;
}

export function shellAllowsExecutionFork(contract: ShellHostContract): boolean {
  return contract.actions.allowExecutionFork;
}

export function shellAllowsComposer(contract: ShellHostContract): boolean {
  return contract.composer.allowComposer;
}

export function shellReadOnlyExecution(contract: ShellHostContract): boolean {
  return contract.composer.readOnlyExecution;
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
