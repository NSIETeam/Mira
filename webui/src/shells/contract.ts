import type { ShellHostContract } from "./types";
import type { ShellDescriptorPayload } from "@/lib/types";

function shellThemeFallback(contract: ShellHostContract): string {
  switch (contract.mode) {
    case "single-execution":
      return "workbench";
    case "review":
      return "review";
    default:
      return contract.mode;
  }
}

export function shellDataAttributes({
  shellDescriptor,
  shellSupportsThreads,
  shellSupportsRuntimeControls,
  shellSupportsFileActivity,
  hostContract,
  layout,
}: {
  shellDescriptor: ShellDescriptorPayload | null;
  shellSupportsThreads: boolean;
  shellSupportsRuntimeControls: boolean;
  shellSupportsFileActivity: boolean;
  hostContract: ShellHostContract;
  layout?: string;
}): Record<string, string> {
  return {
    "data-shell-name": shellDescriptor?.name ?? hostContract.mode,
    "data-shell-theme": shellDescriptor?.theme ?? shellThemeFallback(hostContract),
    "data-shell-description": shellDescriptor?.description ?? "",
    "data-shell-supports-threads": shellSupportsThreads ? "true" : "false",
    "data-shell-supports-runtime-controls": shellSupportsRuntimeControls ? "true" : "false",
    "data-shell-supports-file-activity": shellSupportsFileActivity ? "true" : "false",
    ...(layout ? { "data-shell-layout": layout } : {}),
    "data-shell-mode": hostContract.mode,
    "data-shell-read-only": hostContract.composer.readOnlyExecution ? "true" : "false",
  };
}
