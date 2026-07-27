import { useEffect } from "react";

import type { ExecutionSummary } from "@/lib/types";
import type { ShellView } from "@/shells/host";

interface UseShellPresentationStateOptions {
  activeSession: ExecutionSummary | null;
  activeShellView: ShellView;
  shellSupportsThreads: boolean;
  shellTitle: string;
  headerTitle: string;
  settingsTitle: string;
  appsTitle: string;
  automationsTitle: string;
  skillsTitle: string;
  baseTitle: string;
  formatChatTitle: (title: string) => string;
  showHostChrome: boolean;
  onNewExecution: () => void;
  onOpenSessionSearch: () => void;
}

export function useShellPresentationState({
  activeSession,
  activeShellView,
  shellSupportsThreads,
  shellTitle,
  headerTitle,
  settingsTitle,
  appsTitle,
  automationsTitle,
  skillsTitle,
  baseTitle,
  formatChatTitle,
  showHostChrome,
  onNewExecution,
  onOpenSessionSearch,
}: UseShellPresentationStateOptions) {
  useEffect(() => {
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.defaultPrevented) return;
      const commandShiftO =
        (event.metaKey || event.ctrlKey) && event.shiftKey && !event.altKey;
      if (commandShiftO && event.key.toLowerCase() === "o") {
        event.preventDefault();
        onNewExecution();
        return;
      }
      const plainCommandK =
        (event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey;
      if (!plainCommandK) return;
      if (event.key.toLowerCase() !== "k") return;
      event.preventDefault();
      onOpenSessionSearch();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onNewExecution, onOpenSessionSearch]);

  useEffect(() => {
    if (activeShellView === "settings") {
      document.title = formatChatTitle(settingsTitle);
      return;
    }
    if (activeShellView === "apps") {
      document.title = formatChatTitle(appsTitle);
      return;
    }
    if (activeShellView === "automations") {
      document.title = formatChatTitle(automationsTitle);
      return;
    }
    if (activeShellView === "skills") {
      document.title = formatChatTitle(skillsTitle);
      return;
    }
    if (!shellSupportsThreads) {
      document.title = shellTitle;
      return;
    }
    document.title = activeSession
      ? formatChatTitle(headerTitle)
      : baseTitle;
  }, [
    activeSession,
    activeShellView,
    appsTitle,
    automationsTitle,
    baseTitle,
    formatChatTitle,
    headerTitle,
    settingsTitle,
    shellSupportsThreads,
    shellTitle,
    skillsTitle,
  ]);

  useEffect(() => {
    document.documentElement.classList.toggle("native-host", showHostChrome);
    return () => {
      document.documentElement.classList.remove("native-host");
    };
  }, [showHostChrome]);
}
