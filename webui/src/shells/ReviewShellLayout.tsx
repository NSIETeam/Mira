import { cn } from "@/lib/utils";
import { shellDataAttributes } from "./contract";

import type { ShellViewProps } from "./types";

export function ReviewShellLayout({
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
    fallbackName: "review",
    fallbackTheme: "review",
    layout: "review",
  });

  return (
    <div
      className={cn(
        "relative h-full w-full overflow-hidden bg-[radial-gradient(circle_at_top,#f4f1e8,transparent_48%),linear-gradient(180deg,#fcfbf7_0%,#f6f3ea_100%)]",
        showHostChrome && "host-window-shell",
      )}
      {...shellAttrs}
      aria-label={shellTitle}
    >
      {topChrome}
      <main className="relative h-full w-full overflow-auto">
        <div className="mx-auto flex min-h-full w-full max-w-6xl flex-col px-4 pb-6 pt-4 sm:px-6 lg:px-8">
          <div className="mb-4 flex items-center justify-between gap-4 border-b border-black/8 pb-3">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-black/45">
                Review Shell
              </div>
              <h1 className="text-xl font-semibold tracking-[-0.02em] text-black/80">
                {shellTitle}
              </h1>
            </div>
            <div className="rounded-full border border-black/10 bg-white/70 px-3 py-1 text-xs text-black/55 backdrop-blur">
              Focused output review
            </div>
          </div>
          <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(320px,0.9fr)]">
            <section className="relative min-h-[520px] overflow-hidden rounded-[28px] border border-black/8 bg-white/88 shadow-[0_20px_80px_rgba(0,0,0,0.08)]">
              {chatView}
            </section>
            <aside className="relative min-h-[320px] overflow-hidden rounded-[28px] border border-black/8 bg-white/72 shadow-[0_20px_80px_rgba(0,0,0,0.06)] backdrop-blur">
              {utilityView ?? (
                <div className="flex h-full items-center justify-center px-6 text-center text-sm text-black/45">
                  Review shell keeps context compact and result-focused.
                </div>
              )}
            </aside>
          </div>
        </div>
      </main>
      {overlays}
    </div>
  );
}
