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
  allowPrivilegedRuntimeControls: boolean;
}

export interface ShellHostActionContract {
  allowExecutionFork: boolean;
}

export interface ShellHostComposerContract {
  allowComposer: boolean;
  readOnlyExecution: boolean;
}

export interface ShellHostPrivilegeContract {
  role: "root" | "user" | string;
  canElevate: boolean;
}

export interface ShellHostContract {
  schema: string;
  version: number;
  mode: ShellMode;
  chrome: ShellHostChromeContract;
  surfaces: ShellHostSurfaceContract;
  actions: ShellHostActionContract;
  composer: ShellHostComposerContract;
  privilege: ShellHostPrivilegeContract;
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
