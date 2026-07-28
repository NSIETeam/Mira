import { cn } from "@/lib/utils";
import { shellDataAttributes } from "./contract";

import type { ShellViewProps } from "./types";

export function SingleExecutionShellLayout({
  showHostChrome,
  shellDescriptor,
  shellTitle,
  shellCapabilities,
  hostContract,
  topChrome,
  executionView,
  utilityView,
  overlays,
}: ShellViewProps) {
  const shellAttrs = shellDataAttributes({
    shellDescriptor,
    shellCapabilities,
    hostContract,
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
          {executionView}
          {utilityView}
        </div>
      </main>
      {overlays}
    </div>
  );
}
