import { useCallback } from "react";

import type { SettingsSectionKey } from "@/components/settings/SettingsView";
import {
  shellViewForSettingsSection,
  type ShellRoute,
} from "@/shells/host";

interface UseShellUtilityStateOptions {
  activeKey: string | null;
  sessions: Array<{ key: string }>;
  shellAllowsUtilitySurface: boolean;
  navigate: (route: ShellRoute, options?: { replace?: boolean }) => void;
  setSessionSearchOpen: React.Dispatch<React.SetStateAction<boolean>>;
  setMobileSidebarOpen: React.Dispatch<React.SetStateAction<boolean>>;
  preloadSettingsView: () => void;
}

export function useShellUtilityState({
  activeKey,
  sessions,
  shellAllowsUtilitySurface,
  navigate,
  setSessionSearchOpen,
  setMobileSidebarOpen,
  preloadSettingsView,
}: UseShellUtilityStateOptions) {
  const closeTransientUi = useCallback(() => {
    setSessionSearchOpen(false);
    setMobileSidebarOpen(false);
  }, [setMobileSidebarOpen, setSessionSearchOpen]);

  const onOpenSettings = useCallback(
    (section: SettingsSectionKey = "overview") => {
      if (!shellAllowsUtilitySurface) return;
      closeTransientUi();
      navigate({ view: "settings", activeKey, settingsSection: section });
    },
    [activeKey, closeTransientUi, navigate, shellAllowsUtilitySurface],
  );

  const onSettingsIntent = useCallback(() => {
    preloadSettingsView();
  }, [preloadSettingsView]);

  const onOpenModelSettings = useCallback(() => {
    onOpenSettings("models");
  }, [onOpenSettings]);

  const onOpenApps = useCallback(() => {
    if (!shellAllowsUtilitySurface) return;
    closeTransientUi();
    navigate({ view: "apps", activeKey, settingsSection: "apps" });
  }, [activeKey, closeTransientUi, navigate, shellAllowsUtilitySurface]);

  const onOpenAutomations = useCallback(() => {
    if (!shellAllowsUtilitySurface) return;
    closeTransientUi();
    navigate({ view: "automations", activeKey, settingsSection: "automations" });
  }, [activeKey, closeTransientUi, navigate, shellAllowsUtilitySurface]);

  const onOpenSkills = useCallback(() => {
    if (!shellAllowsUtilitySurface) return;
    closeTransientUi();
    navigate({ view: "skills", activeKey, settingsSection: "skills" });
  }, [activeKey, closeTransientUi, navigate, shellAllowsUtilitySurface]);

  const onSettingsSectionChange = useCallback(
    (section: SettingsSectionKey) => {
      navigate({
        view: shellViewForSettingsSection(section),
        activeKey,
        settingsSection: section,
      });
    },
    [activeKey, navigate],
  );

  const onBackToChat = useCallback(() => {
    setMobileSidebarOpen(false);
    const nextKey = (() => {
      if (!activeKey) return null;
      if (sessions.some((session) => session.key === activeKey)) return activeKey;
      return sessions[0]?.key ?? null;
    })();
    navigate({
      view: "chat",
      activeKey: nextKey,
      settingsSection: "overview",
    });
  }, [activeKey, navigate, sessions, setMobileSidebarOpen]);

  return {
    onOpenSettings,
    onSettingsIntent,
    onOpenModelSettings,
    onOpenApps,
    onOpenAutomations,
    onOpenSkills,
    onSettingsSectionChange,
    onBackToChat,
  };
}
