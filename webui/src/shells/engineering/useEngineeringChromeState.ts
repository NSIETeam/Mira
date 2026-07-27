import { useCallback, useEffect, useRef, useState } from "react";

import { SIDEBAR_STORAGE_KEY } from "@/shells/host";

function readSidebarOpen(): boolean {
  if (typeof window === "undefined") return true;
  try {
    const raw = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    if (raw === null) return true;
    return raw === "1";
  } catch {
    return true;
  }
}

export function useEngineeringChromeState({
  showHostChrome,
  showMainSidebar,
}: {
  showHostChrome: boolean;
  showMainSidebar: boolean;
}) {
  const [hostSidebarOpen, setHostSidebarOpen] = useState<boolean>(readSidebarOpen);
  const [hostSidebarPreviewOpen, setHostSidebarPreviewOpen] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [sessionSearchOpen, setSessionSearchOpen] = useState(false);
  const hostSidebarPreviewCloseTimerRef = useRef<number | null>(null);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        SIDEBAR_STORAGE_KEY,
        hostSidebarOpen ? "1" : "0",
      );
    } catch {
      // ignore storage errors
    }
  }, [hostSidebarOpen]);

  const clearHostSidebarPreviewCloseTimer = useCallback(() => {
    if (hostSidebarPreviewCloseTimerRef.current === null) return;
    window.clearTimeout(hostSidebarPreviewCloseTimerRef.current);
    hostSidebarPreviewCloseTimerRef.current = null;
  }, []);

  const closeHostSidebarPreview = useCallback(() => {
    clearHostSidebarPreviewCloseTimer();
    setHostSidebarPreviewOpen(false);
  }, [clearHostSidebarPreviewCloseTimer]);

  const openHostSidebarPreview = useCallback(() => {
    if (!showHostChrome || !showMainSidebar || hostSidebarOpen) return;
    clearHostSidebarPreviewCloseTimer();
    setHostSidebarPreviewOpen(true);
  }, [
    clearHostSidebarPreviewCloseTimer,
    hostSidebarOpen,
    showHostChrome,
    showMainSidebar,
  ]);

  const scheduleHostSidebarPreviewClose = useCallback(() => {
    clearHostSidebarPreviewCloseTimer();
    if (!showHostChrome || !showMainSidebar || hostSidebarOpen) {
      setHostSidebarPreviewOpen(false);
      return;
    }
    hostSidebarPreviewCloseTimerRef.current = window.setTimeout(() => {
      setHostSidebarPreviewOpen(false);
      hostSidebarPreviewCloseTimerRef.current = null;
    }, 160);
  }, [
    clearHostSidebarPreviewCloseTimer,
    hostSidebarOpen,
    showHostChrome,
    showMainSidebar,
  ]);

  useEffect(() => {
    return () => clearHostSidebarPreviewCloseTimer();
  }, [clearHostSidebarPreviewCloseTimer]);

  useEffect(() => {
    if (!showHostChrome || !showMainSidebar || hostSidebarOpen) {
      closeHostSidebarPreview();
    }
  }, [
    closeHostSidebarPreview,
    hostSidebarOpen,
    showHostChrome,
    showMainSidebar,
  ]);

  const closeHostSidebar = useCallback(() => {
    closeHostSidebarPreview();
    setHostSidebarOpen(false);
  }, [closeHostSidebarPreview]);

  const openHostSidebar = useCallback(() => {
    closeHostSidebarPreview();
    setHostSidebarOpen(true);
  }, [closeHostSidebarPreview]);

  const toggleHostSidebar = useCallback(() => {
    closeHostSidebarPreview();
    setHostSidebarOpen((value) => !value);
  }, [closeHostSidebarPreview]);

  const closeMobileSidebar = useCallback(() => {
    setMobileSidebarOpen(false);
  }, []);

  const toggleSidebar = useCallback(() => {
    const isNativeHost =
      typeof window !== "undefined" &&
      window.matchMedia("(min-width: 1024px)").matches;
    if (isNativeHost) {
      closeHostSidebarPreview();
      setHostSidebarOpen((value) => !value);
    } else {
      setMobileSidebarOpen((value) => !value);
    }
  }, [closeHostSidebarPreview]);

  return {
    hostSidebarOpen,
    hostSidebarPreviewOpen,
    mobileSidebarOpen,
    sessionSearchOpen,
    setMobileSidebarOpen,
    setSessionSearchOpen,
    openHostSidebarPreview,
    scheduleHostSidebarPreviewClose,
    closeHostSidebar,
    openHostSidebar,
    toggleHostSidebar,
    closeMobileSidebar,
    toggleSidebar,
  };
}
