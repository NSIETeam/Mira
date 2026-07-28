import type { ShellHostContract } from "./types";
import { resolveShellRegistration } from "./registry";
import type { ShellDescriptorPayload } from "@/lib/types";

export function normalizedShellHostContract(
  shellDescriptor: ShellDescriptorPayload | null,
): ShellHostContract {
  return resolveShellRegistration(shellDescriptor).hostContract;
}

export function shellDescriptorAllowsKernelConsole(
  shellDescriptor: ShellDescriptorPayload | null,
): boolean {
  return normalizedShellHostContract(shellDescriptor).surfaces.allowKernelConsole;
}

export function shellAllowsPrivilegedRuntimeControls(contract: ShellHostContract): boolean {
  return contract.surfaces.allowPrivilegedRuntimeControls;
}

export function shellDataAttributes({
  shellDescriptor,
  shellSupportsThreads,
  shellSupportsRuntimeControls,
  shellSupportsFileActivity,
  hostContract,
  fallbackTheme,
  layout,
}: {
  shellDescriptor: ShellDescriptorPayload | null;
  shellSupportsThreads: boolean;
  shellSupportsRuntimeControls: boolean;
  shellSupportsFileActivity: boolean;
  hostContract: ShellHostContract;
  fallbackTheme: string;
  layout?: string;
}): Record<string, string> {
  return {
    "data-shell-name": shellDescriptor?.name ?? hostContract.mode,
    "data-shell-theme": shellDescriptor?.theme ?? fallbackTheme,
    "data-shell-description": shellDescriptor?.description ?? "",
    "data-shell-supports-threads": shellSupportsThreads ? "true" : "false",
    "data-shell-supports-runtime-controls": shellSupportsRuntimeControls ? "true" : "false",
    "data-shell-supports-file-activity": shellSupportsFileActivity ? "true" : "false",
    ...(layout ? { "data-shell-layout": layout } : {}),
    "data-shell-mode": hostContract.mode,
    "data-shell-read-only": hostContract.composer.readOnlyExecution ? "true" : "false",
  };
}
