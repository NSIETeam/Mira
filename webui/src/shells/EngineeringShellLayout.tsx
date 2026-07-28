import { cn } from "@/lib/utils";
import { shellDataAttributes } from "./contract";
import type { ShellViewProps } from "./types";

export function EngineeringShellLayout({
  showHostChrome,
  shellDescriptor,
  shellTitle,
  shellCapabilities,
  hostContract,
  topChrome,
  hostSidebarFlow,
  hostSidebarPreview,
  mobileSidebar,
  searchDialog,
  executionView,
  kernelConsole,
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
        "relative h-full w-full overflow-hidden bg-[radial-gradient(circle_at_top,rgba(226,232,240,0.55),rgba(248,250,252,0)_38%),linear-gradient(180deg,#f8fafc_0%,#f1f5f9_100%)]",
        showHostChrome && "host-window-shell",
      )}
      {...shellAttrs}
      aria-label={shellTitle}
    >
      {topChrome}
      <div className="relative flex h-full w-full overflow-hidden pt-12">
        {hostSidebarFlow}
        {hostSidebarPreview}
        {mobileSidebar}
        {searchDialog}
        <main className="relative flex h-full min-w-0 flex-1 flex-col overflow-hidden border-l border-slate-200/70 bg-background/92 shadow-[inset_0_1px_0_rgba(255,255,255,0.65)]">
          {executionView}
          {utilityView}
        </main>
        {kernelConsole}
      </div>
      {overlays}
    </div>
  );
}
