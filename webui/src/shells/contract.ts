import type { ShellHostContract } from "./types";
import type { ShellDescriptorPayload } from "@/lib/types";

const SHELL_THEME_FALLBACKS: Partial<Record<ShellHostContract["mode"], string>> = {
  "single-execution": "workbench",
  review: "review",
};

function dataFlag(value: boolean): string {
  return value ? "true" : "false";
}

function shellThemeFallback(contract: ShellHostContract): string {
  return SHELL_THEME_FALLBACKS[contract.mode] ?? contract.mode;
}

export function shellDataAttributes({
  shellDescriptor,
  shellSupportsThreads,
  shellSupportsRuntimeControls,
  shellSupportsFileActivity,
  hostContract,
}: {
  shellDescriptor: ShellDescriptorPayload | null;
  shellSupportsThreads: boolean;
  shellSupportsRuntimeControls: boolean;
  shellSupportsFileActivity: boolean;
  hostContract: ShellHostContract;
}): Record<string, string> {
  return {
    "data-shell-name": shellDescriptor?.name ?? hostContract.mode,
    "data-shell-theme": shellDescriptor?.theme ?? shellThemeFallback(hostContract),
    "data-shell-description": shellDescriptor?.description ?? "",
    "data-shell-supports-threads": dataFlag(shellSupportsThreads),
    "data-shell-supports-runtime-controls": dataFlag(shellSupportsRuntimeControls),
    "data-shell-supports-file-activity": dataFlag(shellSupportsFileActivity),
    ...(hostContract.mode !== "engineering" ? { "data-shell-layout": hostContract.mode } : {}),
    "data-shell-mode": hostContract.mode,
    "data-shell-read-only": dataFlag(hostContract.composer.readOnlyExecution),
  };
}
