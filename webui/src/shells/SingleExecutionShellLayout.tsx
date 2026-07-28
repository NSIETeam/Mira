import { cn } from "@/lib/utils";
import { shellDataAttributes } from "./contract";

import type { ShellViewProps } from "./types";

export function SingleExecutionShellLayout({
  showHostChrome,
  shellDescriptor,
  shellTitle,
  shellSupportsThreads,
  shellSupportsRuntimeControls,
  shellSupportsFileActivity,
  hostContract,
  topChrome,
  chatView,
  utilityView,
  overlays,
}: ShellViewProps) {
  const shellAttrs = shellDataAttributes({
    shellDescriptor,
    shellSupportsThreads,
    shellSupportsRuntimeControls,
    shellSupportsFileActivity,
    hostContract,
    fallbackName: "single-execution",
    fallbackTheme: "workbench",
    layout: "single-execution",
  });

  return (
    <div
      className={cn(
        "relative h-full w-full overflow-hidden bg-background",
        showHostChrome && "host-window-shell",
      )}
      {...shellAttrs}
      aria-label={shellTitle}
    >
      {topChrome}
      <main className="relative h-full w-full overflow-hidden">
        <div className="absolute inset-0">
          {chatView}
          {utilityView}
        </div>
      </main>
      {overlays}
    </div>
  );
}
