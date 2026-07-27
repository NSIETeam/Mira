import type { ReactNode } from "react";

import type { ShellDescriptorPayload } from "@/lib/types";

export type ShellMode = "engineering" | "single-execution" | "review";

export interface ShellHostChromeContract {
  showSidebarChrome: boolean;
  showSearchDialog: boolean;
}

export interface ShellHostSurfaceContract {
  allowUtilitySurface: boolean;
  allowWorkspaceControls: boolean;
  allowRuntimeModelControls: boolean;
  allowKernelConsole: boolean;
}

export interface ShellHostActionContract {
  allowExecutionFork: boolean;
}

export interface ShellHostComposerContract {
  allowComposer: boolean;
  readOnlyExecution: boolean;
}

export interface ShellHostContract {
  mode: ShellMode;
  showSidebarChrome: boolean;
  showSearchDialog: boolean;
  allowUtilitySurface: boolean;
  allowExecutionFork: boolean;
  allowWorkspaceControls: boolean;
  allowRuntimeModelControls: boolean;
  allowKernelConsole: boolean;
  allowComposer: boolean;
  readOnlyExecution: boolean;
  chrome: ShellHostChromeContract;
  surfaces: ShellHostSurfaceContract;
  actions: ShellHostActionContract;
  composer: ShellHostComposerContract;
}

export interface ShellViewProps {
  showHostChrome: boolean;
  shellDescriptor: ShellDescriptorPayload | null;
  shellTitle: string;
  shellSupportsThreads: boolean;
  shellSupportsRuntimeControls: boolean;
  shellSupportsFileActivity: boolean;
  hostContract: ShellHostContract;
  topChrome?: ReactNode;
  hostSidebarFlow?: ReactNode;
  hostSidebarPreview?: ReactNode;
  mobileSidebar?: ReactNode;
  searchDialog?: ReactNode;
  chatView: ReactNode;
  kernelConsole?: ReactNode;
  utilityView?: ReactNode;
  overlays?: ReactNode;
}
