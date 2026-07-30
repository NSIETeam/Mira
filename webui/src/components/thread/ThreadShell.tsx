import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { useTranslation } from "react-i18next";

import { FilePreviewAvailabilityProvider } from "@/components/FilePreviewAvailabilityContext";
import { FilePreviewPanel } from "@/components/FilePreviewPanel";
import { PromptNavigator } from "@/components/thread/PromptNavigator";
import { ExecutionInfoPopover } from "@/components/thread/ExecutionInfoPopover";
import { ThreadComposer } from "@/components/thread/ThreadComposer";
import type { ModelPresetOption } from "@/components/thread/ModelPresetBadge";
import { ThreadHeader } from "@/components/thread/ThreadHeader";
import { StreamErrorNotice } from "@/components/thread/StreamErrorNotice";
import { ThreadViewport, type ThreadViewportHandle } from "@/components/thread/ThreadViewport";
import { useMiraStream, type SendAttachment, type SendOptions } from "@/hooks/useMiraStream";
import { useExecutionHistory } from "@/hooks/useExecutions";
import {
  ApiError,
  fetchFilePreviewAvailability,
  fetchInstalledCliApps,
  fetchMcpPresets,
  fetchSettings,
  listSlashCommands,
} from "@/lib/api";
import {
  CLI_APPS_CHANGED_EVENT,
  installedCliAppsFromPayload,
  isCliAppsPayload,
} from "@/lib/cli-app-events";
import { cn } from "@/lib/utils";
import {
  MCP_PRESETS_CHANGED_EVENT,
  installedMcpPresetsFromPayload,
  isMcpPresetsPayload,
} from "@/lib/mcp-preset-events";
import { inferProviderFromModelName, providerDisplayLabel } from "@/lib/provider-brand";
import type {
  ExecutionSummary,
  SettingsPayload,
  SlashCommand,
  SkillSummary,
  UIMessage,
  WorkspaceScopePayload,
  WorkspacesPayload,
} from "@/lib/types";
import { projectWebuiThreadMessages } from "@/lib/thread-display-compat";
import { useClient } from "@/providers/ClientProvider";

type MessageShape = Pick<UIMessage, "role" | "kind" | "content">;

function sameMessageShape(a: MessageShape, b: MessageShape): boolean {
  return (
    a.role === b.role
    && (a.kind ?? "") === (b.kind ?? "")
    && a.content === b.content
  );
}

function durableMessageShape(message: UIMessage): MessageShape | null {
  if (message.kind === "trace") return null;
  if (message.role !== "user" && message.role !== "assistant") return null;
  if (message.role === "assistant" && !message.content.trim() && !message.media?.length) {
    return null;
  }
  return {
    role: message.role,
    kind: message.kind,
    content: message.content,
  };
}

function preservesDurableMessages(current: UIMessage[], snapshot: UIMessage[]): boolean {
  // Canonical history refreshes can race with live websocket messages after fork/send.
  // Never accept a refreshed snapshot that drops a user/assistant message already shown.
  const expected = current
    .map(durableMessageShape)
    .filter((message): message is MessageShape => message !== null);
  if (expected.length === 0) return true;
  const candidates = snapshot
    .map(durableMessageShape)
    .filter((message): message is MessageShape => message !== null);

  let cursor = 0;
  for (const message of expected) {
    let found = false;
    while (cursor < candidates.length) {
      const candidate = candidates[cursor];
      cursor += 1;
      if (sameMessageShape(message, candidate)) {
        found = true;
        break;
      }
    }
    if (!found) return false;
  }
  return true;
}

function isStaleThreadSnapshot(current: UIMessage[], snapshot: UIMessage[]): boolean {
  if (current.length === 0) return false;
  if (snapshot.length === 0) return true;
  if (!preservesDurableMessages(current, snapshot)) return true;
  if (snapshot.length >= current.length) return false;
  return snapshot.every((message, index) => sameMessageShape(current[index], message));
}

function latestActiveTurnId(messages: UIMessage[]): string | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.isStreaming && message.turnId) return message.turnId;
  }
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role === "user" && message.turnId) return message.turnId;
  }
  return null;
}

const FILE_PREVIEW_DEFAULT_WIDTH = 544;
const FILE_PREVIEW_MIN_WIDTH = 360;
const FILE_PREVIEW_MAX_WIDTH = 860;
const FILE_PREVIEW_MIN_MAIN_WIDTH = 420;
const FILE_PREVIEW_CLOSE_ANIMATION_MS = 320;

type FilePreviewAvailabilityCacheEntry = {
  available?: boolean;
  promise: Promise<boolean>;
  revision: number;
};

function clampFilePreviewWidth(width: number, maxWidth: number): number {
  return Math.min(Math.max(width, FILE_PREVIEW_MIN_WIDTH), maxWidth);
}

function maxFilePreviewWidth(containerWidth: number): number {
  return Math.max(
    FILE_PREVIEW_MIN_WIDTH,
    Math.min(FILE_PREVIEW_MAX_WIDTH, containerWidth - FILE_PREVIEW_MIN_MAIN_WIDTH),
  );
}

interface ThreadShellProps {
  session?: ExecutionSummary | null;
  execution?: ExecutionSummary | null;
  title: string;
  onToggleSidebar?: () => void;
  onGoHome?: () => void;
  onNewExecution?: () => void;
  onCreateExecution?: (workspaceScope?: WorkspaceScopePayload | null) => Promise<string | null>;
  onForkExecution?: (sourceChatId: string, beforeUserIndex: number) => Promise<string | null>;
  onCreateChat?: (workspaceScope?: WorkspaceScopePayload | null) => Promise<string | null>;
  onForkChat?: (sourceChatId: string, beforeUserIndex: number) => Promise<string | null>;
  onTurnEnd?: () => void;
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
  hideSidebarToggleForHostChrome?: boolean;
  hostChromeTitleInset?: boolean;
  hideThemeButton?: boolean;
  hideHeader?: boolean;
  workspaceScope?: WorkspaceScopePayload | null;
  workspaceDefaultScope?: WorkspaceScopePayload | null;
  workspaceControls?: WorkspacesPayload["controls"] | null;
  workspaceScopeDisabled?: boolean;
  workspaceError?: string | null;
  onWorkspaceScopeChange?: (scope: WorkspaceScopePayload) => void;
  settingsSnapshot?: SettingsPayload | null;
  onOpenModelSettings?: () => void;
  supportsThreads?: boolean;
  supportsRuntimeControls?: boolean;
  supportsFileActivity?: boolean;
  allowComposer?: boolean;
  readOnlyExecution?: boolean;
  shellDescription?: string | null;
  skills?: SkillSummary[];
}

function toModelBadgeLabel(modelName: string | null): string | null {
  if (!modelName) return null;
  const trimmed = modelName.trim();
  if (!trimmed) return null;
  const leaf = trimmed.split("/").pop() ?? trimmed;
  return leaf || trimmed;
}

interface ModelBadgeInfo {
  label: string | null;
  model: string | null;
  provider: string | null;
  providerLabel: string | null;
  needsSetup: boolean;
}

function modelPresetForBadge(
  settings: SettingsPayload | null,
  scopedPreset: string | null,
): SettingsPayload["model_presets"][number] | null {
  if (!settings) return null;
  if (scopedPreset) {
    return settings.model_presets.find((preset) => preset.name === scopedPreset) ?? null;
  }
  const configured = settings.agent.model_preset || "default";
  return (
    settings.model_presets.find((preset) => preset.name === configured)
    ?? settings.model_presets.find((preset) => preset.active)
    ?? null
  );
}

function toModelBadgeInfo(
  modelName: string | null,
  settings: SettingsPayload | null,
  modelPreset: string | null = null,
): ModelBadgeInfo {
  const scopedPreset = modelPreset?.trim() || null;
  const preset = modelPresetForBadge(settings, scopedPreset);
  const model = scopedPreset
    ? preset?.model || null
    : settings?.agent.model || modelName || null;
  const label = preset?.label?.trim() || scopedPreset || toModelBadgeLabel(model);
  const rawProvider = preset?.provider
    || (!scopedPreset ? settings?.agent.provider : null)
    || null;
  const provider = rawProvider === "auto"
    ? preset?.resolved_provider
      || (!scopedPreset ? settings?.agent.resolved_provider : null)
      || null
    : rawProvider || inferProviderFromModelName(model);
  const providerRow = provider
    ? settings?.providers.find((item) => item.name === provider)
    : null;
  const needsSetup = Boolean(
    settings && (!model || !provider || !providerRow || !providerRow.configured),
  );
  return {
    label,
    model: toModelBadgeLabel(model),
    provider,
    providerLabel: provider ? providerDisplayLabel(settings?.providers ?? [], provider) : null,
    needsSetup,
  };
}

function modelPresetOptionsFromSettings(
  settings: SettingsPayload | null,
): ModelPresetOption[] {
  if (!settings) return [];
  const order = new Map(
    (settings.model_call_order ?? []).map((name, index) => [name.trim(), index]),
  );
  return settings.model_presets
    .filter((preset) => !preset.is_default && preset.name.trim())
    .sort((a, b) => (
      (order.get(a.name.trim()) ?? Number.POSITIVE_INFINITY)
      - (order.get(b.name.trim()) ?? Number.POSITIVE_INFINITY)
    ))
    .map((preset) => {
      const name = preset.name.trim();
      return {
        name,
        label: preset.label?.trim() || name,
        model: preset.model,
        provider: preset.resolved_provider || preset.provider,
      };
    });
}

const HERO_GREETING_KEYS = [
  "thread.empty.greetings.workOn",
  "thread.empty.greetings.start",
  "thread.empty.greetings.build",
  "thread.empty.greetings.tackle",
] as const;

function HeroGreeting({ text }: { text: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useLayoutEffect(() => {
    const container = containerRef.current;
    const heading = headingRef.current;
    if (!container || !heading) return;

    const fitToWidth = () => {
      heading.style.removeProperty("font-size");
      const availableWidth = container.clientWidth;
      if (availableWidth <= 0) return;

      const naturalWidth = heading.scrollWidth;
      const maximumFontSize = Number.parseFloat(window.getComputedStyle(heading).fontSize);
      if (
        naturalWidth <= availableWidth
        || !Number.isFinite(maximumFontSize)
        || maximumFontSize <= 0
      ) {
        return;
      }

      const fittedFontSize = Math.max(
        12,
        Math.floor(maximumFontSize * ((availableWidth - 2) / naturalWidth) * 100) / 100,
      );
      heading.style.fontSize = `${fittedFontSize}px`;
    };

    fitToWidth();

    let lastObservedWidth = container.clientWidth;
    const resizeObserver = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(([entry]) => {
          const nextWidth = entry?.contentRect.width ?? container.clientWidth;
          if (nextWidth === lastObservedWidth) return;
          lastObservedWidth = nextWidth;
          fitToWidth();
        });
    resizeObserver?.observe(container);
    window.addEventListener("resize", fitToWidth);

    let cancelled = false;
    void document.fonts?.ready.then(() => {
      if (!cancelled) fitToWidth();
    });

    return () => {
      cancelled = true;
      resizeObserver?.disconnect();
      window.removeEventListener("resize", fitToWidth);
    };
  }, [text]);

  return (
    <div ref={containerRef} className="min-w-0 w-full max-w-[36rem] overflow-hidden">
      <h1
        ref={headingRef}
        data-testid="hero-greeting"
        className="text-balance break-words text-[28px] font-normal leading-[1.12] tracking-normal text-foreground sm:text-[38px] sm:leading-tight"
      >
        {text}
      </h1>
    </div>
  );
}

function randomHeroGreetingKey(): (typeof HERO_GREETING_KEYS)[number] {
  const index = Math.floor(Math.random() * HERO_GREETING_KEYS.length);
  return HERO_GREETING_KEYS[index] ?? HERO_GREETING_KEYS[0];
}

interface PendingFirstMessage {
  content: string;
  images?: SendAttachment[];
  options?: SendOptions;
}

interface InstalledSettingItemsOptions<Payload, Item> {
  token: string;
  eventName: string;
  fetchPayload: (token: string) => Promise<Payload>;
  isPayload: (value: unknown) => value is Payload;
  selectItems: (payload: Payload) => Item[];
}

function useInstalledSettingItems<Payload, Item>({
  token,
  eventName,
  fetchPayload,
  isPayload,
  selectItems,
}: InstalledSettingItemsOptions<Payload, Item>): Item[] {
  const [items, setItems] = useState<Item[]>([]);

  const refresh = useCallback(async (isCancelled?: () => boolean) => {
    try {
      const payload = await fetchPayload(token);
      if (!isCancelled?.()) setItems(selectItems(payload));
    } catch {
      // Keep the last successful catalog during transient focus/visibility refresh failures.
    }
  }, [fetchPayload, selectItems, token]);

  useEffect(() => {
    let cancelled = false;
    void refresh(() => cancelled);

    const refreshOnFocus = () => {
      if (document.visibilityState === "hidden") return;
      void refresh();
    };
    const refreshOnChanged = (event: Event) => {
      const payload = (event as CustomEvent<unknown>).detail;
      if (isPayload(payload)) {
        setItems(selectItems(payload));
        return;
      }
      void refresh();
    };

    window.addEventListener("focus", refreshOnFocus);
    document.addEventListener("visibilitychange", refreshOnFocus);
    window.addEventListener(eventName, refreshOnChanged);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", refreshOnFocus);
      document.removeEventListener("visibilitychange", refreshOnFocus);
      window.removeEventListener(eventName, refreshOnChanged);
    };
  }, [eventName, isPayload, refresh, selectItems]);

  return items;
}

export function ThreadShell({
  session = null,
  execution = null,
  title,
  onToggleSidebar,
  onCreateExecution,
  onCreateChat,
  onForkExecution,
  onForkChat,
  onTurnEnd,
  theme = "light",
  onToggleTheme = () => {},
  hideSidebarToggleForHostChrome = false,
  hostChromeTitleInset = false,
  hideThemeButton = false,
  hideHeader = false,
  workspaceScope = null,
  workspaceDefaultScope = null,
  workspaceControls = null,
  workspaceScopeDisabled = false,
  workspaceError = null,
  onWorkspaceScopeChange,
  settingsSnapshot = null,
  onOpenModelSettings,
  supportsThreads = true,
  supportsRuntimeControls = true,
  supportsFileActivity = true,
  allowComposer = true,
  readOnlyExecution = false,
  shellDescription = null,
  skills = [],
}: ThreadShellProps) {
  const activeExecution = execution ?? session;
  const handleCreateExecution = onCreateExecution ?? onCreateChat;
  const handleForkExecution = onForkExecution ?? onForkChat;
  const { t, i18n } = useTranslation();
  const isChineseLocale = (i18n.resolvedLanguage ?? i18n.language ?? "").toLowerCase().startsWith("zh");
  const chatId = activeExecution?.chatId ?? null;
  const historyKey = activeExecution?.key ?? null;
  const {
    messages: historical,
    loading,
    loadingOlder,
    loadOlder,
    hasMoreBefore,
    userMessageOffset,
    hasPendingToolCalls,
    refresh: refreshHistory,
    version: historyVersion,
    forkBoundaryMessageCount,
  } = useExecutionHistory(historyKey);
  const { client, ingressLimits, modelName, token } = useClient();
  const [fallbackModelName, setFallbackModelName] = useState<string | null>(null);
  const [booting, setBooting] = useState(false);
  const [slashCommands, setSlashCommands] = useState<SlashCommand[]>([]);
  const cliApps = useInstalledSettingItems({
    token,
    eventName: CLI_APPS_CHANGED_EVENT,
    fetchPayload: fetchInstalledCliApps,
    isPayload: isCliAppsPayload,
    selectItems: installedCliAppsFromPayload,
  });
  const mcpPresets = useInstalledSettingItems({
    token,
    eventName: MCP_PRESETS_CHANGED_EVENT,
    fetchPayload: fetchMcpPresets,
    isPayload: isMcpPresetsPayload,
    selectItems: installedMcpPresetsFromPayload,
  });
  const [settings, setSettings] = useState<SettingsPayload | null>(settingsSnapshot);
  const [heroGreetingKey, setHeroGreetingKey] = useState(randomHeroGreetingKey);
  const [submittedViewportTurnId, setSubmittedViewportTurnId] = useState<string | null>(null);
  const [filePreviewPath, setFilePreviewPath] = useState<string | null>(null);
  const [filePreviewClosing, setFilePreviewClosing] = useState(false);
  const [filePreviewWidth, setFilePreviewWidth] = useState(FILE_PREVIEW_DEFAULT_WIDTH);
  const [quotedContext, setQuotedContext] = useState<string | null>(null);
  const [composerFocusSignal, setComposerFocusSignal] = useState(0);
  const shellRef = useRef<HTMLElement | null>(null);
  const filePreviewWidthRef = useRef(FILE_PREVIEW_DEFAULT_WIDTH);
  const filePreviewCloseTimerRef = useRef<number | null>(null);
  const pendingFirstRef = useRef<PendingFirstMessage | null>(null);
  const [pendingFirstTargetChatId, setPendingFirstTargetChatId] = useState<string | null>(null);
  const viewportRef = useRef<ThreadViewportHandle | null>(null);
  const activeViewportTurnByChatIdRef = useRef<Map<string, string>>(new Map());
  const messageCacheRef = useRef<Map<string, UIMessage[]>>(new Map());
  /** Last chatId we associated with the in-memory thread (for cache-on-switch). */
  const prevChatIdForCacheRef = useRef<string | null>(null);
  /** Skip one message-cache write right after chatId changes (messages may not match yet). */
  const skipLayoutCacheRef = useRef(false);
  const appliedHistoryVersionRef = useRef<Map<string, number>>(new Map());
  const pendingCanonicalHydrateRef = useRef<Set<string>>(new Set());
  const sessionKeyByChatIdRef = useRef<Map<string, string>>(new Map());

  const initial = useMemo(() => {
    if (!chatId) return historical;
    return messageCacheRef.current.get(chatId) ?? historical;
  }, [chatId, historical]);
  const handleTurnEnd = useCallback(() => {
    if (chatId) activeViewportTurnByChatIdRef.current.delete(chatId);
    setSubmittedViewportTurnId(null);
    setFallbackModelName(null);
    onTurnEnd?.();
  }, [chatId, onTurnEnd]);
  const {
    messages,
    messagesReady,
    isStreaming,
    runStartedAt,
    goalState,
    send,
    transcribeAudio,
    stop,
    setMessages,
    streamError,
    dismissStreamError,
  } = useMiraStream(chatId, initial, hasPendingToolCalls, handleTurnEnd);

  useEffect(() => {
    if (chatId && historyKey) sessionKeyByChatIdRef.current.set(chatId, historyKey);
  }, [chatId, historyKey]);

  useEffect(() => {
    filePreviewWidthRef.current = filePreviewWidth;
  }, [filePreviewWidth]);

  useEffect(() => {
    if (filePreviewCloseTimerRef.current !== null) {
      window.clearTimeout(filePreviewCloseTimerRef.current);
      filePreviewCloseTimerRef.current = null;
    }
    setFilePreviewClosing(false);
    setFilePreviewPath(null);
    setQuotedContext(null);
    setSubmittedViewportTurnId(null);
  }, [historyKey]);

  const handleQuoteSelection = useCallback((text: string) => {
    setQuotedContext(text);
    setComposerFocusSignal((value) => value + 1);
  }, []);

  useEffect(() => {
    return () => {
      if (filePreviewCloseTimerRef.current !== null) {
        window.clearTimeout(filePreviewCloseTimerRef.current);
      }
    };
  }, []);

  const displayMessages = useMemo(() => projectWebuiThreadMessages(messages), [messages]);
  const currentRunStartedAt = messagesReady ? runStartedAt : null;
  const currentGoalState = messagesReady ? goalState : undefined;
  const turnActive = messagesReady && (isStreaming || currentRunStartedAt !== null);
  const restoredViewportTurnId = useMemo(
    () => turnActive ? latestActiveTurnId(displayMessages) : null,
    [displayMessages, turnActive],
  );
  const rememberedViewportTurnId = chatId
    ? activeViewportTurnByChatIdRef.current.get(chatId) ?? null
    : null;
  const viewportTurnId = messagesReady && turnActive
    ? rememberedViewportTurnId ?? restoredViewportTurnId
    : null;
  const activeTurnStartedHere =
    viewportTurnId !== null && viewportTurnId === submittedViewportTurnId;
  useEffect(() => {
    if (!chatId || !messagesReady || turnActive) return;
    activeViewportTurnByChatIdRef.current.delete(chatId);
    setSubmittedViewportTurnId((current) =>
      current === rememberedViewportTurnId ? null : current,
    );
  }, [chatId, messagesReady, rememberedViewportTurnId, turnActive]);
  const filePreviewAvailabilityCache = useMemo(
    () => new Map<string, FilePreviewAvailabilityCacheEntry>(),
    [historyKey, token],
  );
  const filePreviewAvailabilityRevision = displayMessages.length;
  const resolveFilePreviewAvailability = useCallback((path: string) => {
    if (!historyKey) return Promise.resolve(false);
    const cached = filePreviewAvailabilityCache.get(path);
    if (
      cached
      && (cached.available !== false || cached.revision === filePreviewAvailabilityRevision)
    ) {
      return cached.promise;
    }
    const pending = fetchFilePreviewAvailability(token, historyKey, path).catch(
      (error: unknown) => {
        if (error instanceof ApiError) {
          if (error.status === 404 && /API route not found/i.test(error.message)) {
            return true;
          }
          if ([400, 403, 404, 415].includes(error.status)) return false;
        }
        return false;
      },
    );
    const entry: FilePreviewAvailabilityCacheEntry = {
      promise: pending,
      revision: filePreviewAvailabilityRevision,
    };
    filePreviewAvailabilityCache.set(path, entry);
    void pending.then((available) => {
      if (filePreviewAvailabilityCache.get(path) === entry) {
        entry.available = available;
      }
    });
    return pending;
  }, [
    filePreviewAvailabilityCache,
    filePreviewAvailabilityRevision,
    historyKey,
    token,
  ]);

  const showHeroComposer = displayMessages.length === 0 && !loading;
  const wasShowingHeroComposerRef = useRef(showHeroComposer);
  const sessionModelPreset = session?.modelPreset?.trim() || null;
  const [localModelPreset, setLocalModelPreset] = useState<string | null>(null);
  useEffect(() => {
    setLocalModelPreset(null);
  }, [session?.key, sessionModelPreset]);
  const activeModelPreset = (
    localModelPreset
    || sessionModelPreset
    || settings?.agent.model_preset
    || "default"
  );
  const handleModelPresetChange = useCallback((name: string) => {
    setLocalModelPreset(name);
    if (chatId) {
      void client.sendSystemCommand(chatId, `/model ${name}`).catch(() => {});
    }
  }, [chatId, client]);
  const modelPresetOptions = useMemo(
    () => modelPresetOptionsFromSettings(settings),
    [settings],
  );
  const modelBadge = useMemo(
    () => toModelBadgeInfo(modelName, settings, activeModelPreset),
    [activeModelPreset, modelName, settings],
  );
  const modelBadgeLabel = modelBadge.needsSetup
    ? t("thread.composer.modelNotConfigured", { defaultValue: "Model not configured" })
    : modelBadge.label;
  useEffect(() => {
    if (showHeroComposer && !wasShowingHeroComposerRef.current) {
      setHeroGreetingKey(randomHeroGreetingKey());
    }
    wasShowingHeroComposerRef.current = showHeroComposer;
  }, [showHeroComposer]);

  const withWorkspaceScope = useCallback(
    (options?: SendOptions): SendOptions | undefined => {
      if (!workspaceScope) return options;
      return {
        ...(options ?? {}),
        workspaceScope,
      };
    },
    [workspaceScope],
  );

  const refreshModelSettings = useCallback(async () => {
    try {
      setSettings(await fetchSettings(token));
    } catch {
      if (!settingsSnapshot) setSettings(null);
    }
  }, [settingsSnapshot, token]);

  useEffect(() => {
    if (settingsSnapshot) {
      setSettings(settingsSnapshot);
      return;
    }
    void refreshModelSettings();
  }, [refreshModelSettings, settingsSnapshot]);

  useEffect(() => {
    return client.onRuntimeModelUpdate(() => {
      void refreshModelSettings();
    });
  }, [client, refreshModelSettings]);

  useEffect(() => {
    if (!chatId) {
      setFallbackModelName(null);
      return;
    }
    setFallbackModelName(null);
    return client.onKernelExecution(chatId, (event) => {
      if (event.type !== "status" || event.state !== "running") return;
      const metadata = event.metadata;
      if (!metadata || typeof metadata !== "object") return;
      const modelName = "model_name" in metadata ? metadata.model_name : undefined;
      if (typeof modelName !== "string") return;
      setFallbackModelName(modelName);
    });
  }, [chatId, client]);

  useEffect(() => {
    if (!chatId || loading) return;
    const cached = messageCacheRef.current.get(chatId);
    const appliedVersion = appliedHistoryVersionRef.current.get(chatId) ?? 0;
    const hasPendingCanonicalHydrate = pendingCanonicalHydrateRef.current.has(chatId);
    const hasNewCanonicalHistory = hasPendingCanonicalHydrate && historyVersion > appliedVersion;
    // When the user switches away and back, keep the local in-memory thread
    // state (including not-yet-persisted messages) instead of replacing it with
    // whatever the history endpoint currently knows about. Once a fresh
    // canonical replay arrives (e.g. after ``session_updated`` refresh), prefer it
    // so rendering converges to the same shape as a manual refresh.
    setMessages((prev) => {
      const normalizedHistory = projectWebuiThreadMessages(historical);
      const keepLiveMessages = (messagesToKeep: UIMessage[]) => {
        const projected = projectWebuiThreadMessages(messagesToKeep);
        messageCacheRef.current.set(chatId, projected);
        return projected;
      };
      if (hasNewCanonicalHistory && historical.length > 0) {
        if (isStaleThreadSnapshot(prev, normalizedHistory)) return keepLiveMessages(prev);
        pendingCanonicalHydrateRef.current.delete(chatId);
        appliedHistoryVersionRef.current.set(chatId, historyVersion);
        messageCacheRef.current.set(chatId, normalizedHistory);
        return normalizedHistory;
      }
      if (cached && cached.length > 0) {
        if (
          normalizedHistory.length > cached.length
          && !isStaleThreadSnapshot(prev, normalizedHistory)
        ) {
          messageCacheRef.current.set(chatId, normalizedHistory);
          appliedHistoryVersionRef.current.set(chatId, historyVersion);
          return normalizedHistory;
        }
        if (isStaleThreadSnapshot(prev, cached)) return keepLiveMessages(prev);
        return cached;
      }
      if (isStaleThreadSnapshot(prev, normalizedHistory)) return keepLiveMessages(prev);
      appliedHistoryVersionRef.current.set(chatId, historyVersion);
      if (normalizedHistory.length > 0) messageCacheRef.current.set(chatId, normalizedHistory);
      return normalizedHistory;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, chatId, historical, historyVersion]);

  useEffect(() => {
    if (!chatId) return;
    return client.onSessionUpdate((updatedChatId, scope) => {
      if (updatedChatId !== chatId) return;
      if (scope === "metadata") return;
      // A turn-end thread refresh can arrive while the viewport is easing the
      // final layout change. User-driven scrolling already disables following,
      // so keep an active programmatic follow alive across canonical hydration.
      pendingCanonicalHydrateRef.current.add(chatId);
      refreshHistory();
    });
  }, [chatId, client, refreshHistory]);

  useEffect(() => {
    if (chatId) return;
    setMessages(projectWebuiThreadMessages(historical));
  }, [chatId, historical, setMessages]);

  useLayoutEffect(() => {
    if (chatId) {
      const prev = prevChatIdForCacheRef.current;
      if (prev && prev !== chatId) {
        messageCacheRef.current.set(prev, displayMessages);
        skipLayoutCacheRef.current = true;
      }
      prevChatIdForCacheRef.current = chatId;
    } else {
      if (prevChatIdForCacheRef.current) {
        messageCacheRef.current.set(
          prevChatIdForCacheRef.current,
          displayMessages,
        );
        skipLayoutCacheRef.current = true;
      }
      prevChatIdForCacheRef.current = null;
    }
  }, [chatId, displayMessages]);

  // Persist thread to in-memory cache after paint so ``useMiraStream``'s execution switch
  // ``useEffect`` reset has flushed; ``skipLayoutCacheRef`` drops the first run that still
  // sees the *previous* execution's ``messages`` (avoids stale rows leaking across sessions).
  useEffect(() => {
    if (!chatId) {
      return;
    }
    if (skipLayoutCacheRef.current) {
      skipLayoutCacheRef.current = false;
      return;
    }
    if (loading) {
      return;
    }
    messageCacheRef.current.set(chatId, displayMessages);
  }, [chatId, displayMessages, loading]);

  // The landing composer queues the first message while `new_chat` is in flight.
  // Only the execution created for that send may consume it; selecting another execution
  // while creation is pending must not leak the message there.
  useEffect(() => {
    if (!chatId || pendingFirstTargetChatId !== chatId) return;
    const pending = pendingFirstRef.current;
    if (!pending) {
      setPendingFirstTargetChatId(null);
      return;
    }
    pendingFirstRef.current = null;
    setPendingFirstTargetChatId(null);
    const submitted = send(pending.content, pending.images, pending.options);
    if (submitted && !submitted.sideChannel) {
      activeViewportTurnByChatIdRef.current.set(chatId, submitted.turnId);
      setSubmittedViewportTurnId(submitted.turnId);
    }
    setBooting(false);
  }, [chatId, pendingFirstTargetChatId, send]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const commands = await listSlashCommands(token);
        if (!cancelled) setSlashCommands(commands);
      } catch {
        if (!cancelled) setSlashCommands([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const handleWelcomeSend = useCallback(
    async (content: string, images?: SendAttachment[], options?: SendOptions) => {
      if (booting) return;
      setBooting(true);
      pendingFirstRef.current = { content, images, options: withWorkspaceScope(options) };
      setPendingFirstTargetChatId(null);
      const newId = await handleCreateExecution?.(workspaceScope);
      if (!newId) {
        pendingFirstRef.current = null;
        setPendingFirstTargetChatId(null);
        setBooting(false);
        return;
      }
      if (localModelPreset) {
        await client.sendSystemCommand(newId, `/model ${localModelPreset}`).catch(() => {});
      }
      setPendingFirstTargetChatId(newId);
    },
    [booting, client, handleCreateExecution, localModelPreset, withWorkspaceScope, workspaceScope],
  );

  const handleThreadSend = useCallback(
    (content: string, images?: SendAttachment[], options?: SendOptions) => {
      setFallbackModelName(null);
      const submitted = send(content, images, withWorkspaceScope(options));
      if (chatId && submitted && !submitted.sideChannel) {
        activeViewportTurnByChatIdRef.current.set(chatId, submitted.turnId);
        setSubmittedViewportTurnId(submitted.turnId);
      }
    },
    [chatId, send, withWorkspaceScope],
  );

  const handleOpenFilePreview = useCallback((path: string) => {
    if (filePreviewCloseTimerRef.current !== null) {
      window.clearTimeout(filePreviewCloseTimerRef.current);
      filePreviewCloseTimerRef.current = null;
    }
    setFilePreviewClosing(false);
    setFilePreviewPath(path);
  }, []);

  const handleCloseFilePreview = useCallback(() => {
    if (!filePreviewPath || filePreviewClosing) return;
    setFilePreviewClosing(true);
    filePreviewCloseTimerRef.current = window.setTimeout(() => {
      filePreviewCloseTimerRef.current = null;
      setFilePreviewPath(null);
      setFilePreviewClosing(false);
    }, FILE_PREVIEW_CLOSE_ANIMATION_MS);
  }, [filePreviewClosing, filePreviewPath]);

  const handleFilePreviewResizeStart = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    const panel = event.currentTarget.closest<HTMLElement>("[data-file-preview-panel]");
    const shellRect = shellRef.current?.getBoundingClientRect();
    const rightEdge = shellRect?.right ?? window.innerWidth;
    const maxWidth = maxFilePreviewWidth(shellRect?.width ?? window.innerWidth);
    const originalBodyCursor = document.body.style.cursor;
    const originalBodyUserSelect = document.body.style.userSelect;
    const originalPanelTransition = panel?.style.transition ?? "";
    let nextWidth = filePreviewWidthRef.current;
    let frame: number | null = null;

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    if (panel) panel.style.transition = "none";

    const applyWidth = (clientX: number) => {
      nextWidth = clampFilePreviewWidth(rightEdge - clientX, maxWidth);
      filePreviewWidthRef.current = nextWidth;
      if (frame !== null) return;
      frame = window.requestAnimationFrame(() => {
        frame = null;
        panel?.style.setProperty("--file-preview-width", `${nextWidth}px`);
        panel?.style.setProperty("--file-preview-slot-width", `${nextWidth}px`);
      });
    };
    const handlePointerMove = (moveEvent: PointerEvent) => {
      moveEvent.preventDefault();
      applyWidth(moveEvent.clientX);
    };
    const handlePointerUp = () => {
      if (frame !== null) {
        window.cancelAnimationFrame(frame);
        frame = null;
      }
      panel?.style.setProperty("--file-preview-width", `${nextWidth}px`);
      panel?.style.setProperty("--file-preview-slot-width", `${nextWidth}px`);
      if (panel) panel.style.transition = originalPanelTransition;
      setFilePreviewWidth(nextWidth);
      document.body.style.cursor = originalBodyCursor;
      document.body.style.userSelect = originalBodyUserSelect;
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
    };

    applyWidth(event.clientX);
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);
  }, []);

  useEffect(() => {
    if (!filePreviewPath) return;
    const clampToShell = () => {
      const shellWidth = shellRef.current?.getBoundingClientRect().width ?? window.innerWidth;
      const maxWidth = maxFilePreviewWidth(shellWidth);
      const nextWidth = clampFilePreviewWidth(filePreviewWidthRef.current, maxWidth);
      filePreviewWidthRef.current = nextWidth;
      setFilePreviewWidth(nextWidth);
    };
    clampToShell();
    window.addEventListener("resize", clampToShell);
    return () => {
      window.removeEventListener("resize", clampToShell);
    };
  }, [filePreviewPath]);

  useEffect(() => {
    if (supportsFileActivity || !filePreviewPath) return;
    if (filePreviewCloseTimerRef.current !== null) {
      window.clearTimeout(filePreviewCloseTimerRef.current);
      filePreviewCloseTimerRef.current = null;
    }
    setFilePreviewClosing(false);
    setFilePreviewPath(null);
  }, [filePreviewPath, supportsFileActivity]);

  const handleForkFromMessage = useCallback(
    async (beforeUserIndex: number) => {
      if (!chatId || !handleForkExecution) return;
      const forkedChatId = await handleForkExecution(chatId, beforeUserIndex);
      if (!forkedChatId) return;
      messageCacheRef.current.delete(forkedChatId);
      appliedHistoryVersionRef.current.delete(forkedChatId);
      pendingCanonicalHydrateRef.current.add(forkedChatId);
    },
    [chatId, handleForkExecution],
  );

  const composer = allowComposer ? (
    <>
      {streamError ? (
        <StreamErrorNotice
          error={streamError}
          onDismiss={dismissStreamError}
        />
      ) : null}
      {activeExecution ? (
        <ThreadComposer
          onSend={handleThreadSend}
          disabled={!chatId}
          isStreaming={turnActive}
          placeholder={
            showHeroComposer
              ? t("thread.composer.placeholderHero")
              : t("thread.composer.placeholderThread")
          }
          modelLabel={modelBadgeLabel}
          modelDetail={modelBadge.model}
          modelPreset={activeModelPreset}
          modelPresets={modelPresetOptions}
          onModelPresetChange={handleModelPresetChange}
          modelProvider={modelBadge.provider}
          modelProviderLabel={modelBadge.providerLabel}
          modelNeedsSetup={modelBadge.needsSetup}
          fallbackModelName={fallbackModelName}
          onModelBadgeClick={
            supportsRuntimeControls && modelBadge.needsSetup
              ? onOpenModelSettings
              : undefined
          }
          showRuntimeControls={supportsRuntimeControls}
          variant={showHeroComposer ? "hero" : "thread"}
          slashCommands={slashCommands}
          cliApps={cliApps}
          mcpPresets={mcpPresets}
          skills={skills}
          onStop={stop}
          onTranscribeAudio={transcribeAudio}
          runStartedAt={currentRunStartedAt}
          goalState={currentGoalState}
          workspaceScope={workspaceScope}
          workspaceDefaultScope={workspaceDefaultScope}
          workspaceControls={workspaceControls}
          workspaceScopeDisabled={workspaceScopeDisabled}
          workspaceError={workspaceError}
          onWorkspaceScopeChange={onWorkspaceScopeChange}
          pendingQueueKey={chatId}
          transcriptionProvider={settingsSnapshot?.transcription?.provider}
          ingressLimits={ingressLimits}
          quotedContext={quotedContext}
          focusRequest={composerFocusSignal}
          onQuotedContextChange={setQuotedContext}
        />
      ) : (
        <ThreadComposer
          onSend={handleWelcomeSend}
          disabled={booting}
          isStreaming={turnActive}
          placeholder={
            booting
              ? t("thread.composer.placeholderOpening")
              : t("thread.composer.placeholderHero")
          }
          modelLabel={modelBadgeLabel}
          modelDetail={modelBadge.model}
          modelPreset={activeModelPreset}
          modelPresets={modelPresetOptions}
          onModelPresetChange={handleModelPresetChange}
          modelProvider={modelBadge.provider}
          modelProviderLabel={modelBadge.providerLabel}
          modelNeedsSetup={modelBadge.needsSetup}
          fallbackModelName={fallbackModelName}
          onModelBadgeClick={
            supportsRuntimeControls && modelBadge.needsSetup
              ? onOpenModelSettings
              : undefined
          }
          showRuntimeControls={supportsRuntimeControls}
          variant="hero"
          slashCommands={slashCommands}
          cliApps={cliApps}
          mcpPresets={mcpPresets}
          skills={skills}
          runStartedAt={currentRunStartedAt}
          onTranscribeAudio={transcribeAudio}
          goalState={currentGoalState}
          workspaceScope={workspaceScope}
          workspaceDefaultScope={workspaceDefaultScope}
          workspaceControls={workspaceControls}
          workspaceScopeDisabled={workspaceScopeDisabled}
          workspaceError={workspaceError}
          onWorkspaceScopeChange={onWorkspaceScopeChange}
          transcriptionProvider={settingsSnapshot?.transcription?.provider}
          ingressLimits={ingressLimits}
        />
      )}
    </>
  ) : null;

  const capabilityBadges = [
    readOnlyExecution ? (isChineseLocale ? "只读" : "read-only") : (isChineseLocale ? "可交互" : "interactive"),
    supportsRuntimeControls ? (isChineseLocale ? "运行控制" : "runtime-control") : (isChineseLocale ? "固定运行" : "fixed-runtime"),
  ];
  const shellPosture = [
    allowComposer ? (isChineseLocale ? "可输入" : "operator ready") : (isChineseLocale ? "仅观察" : "observer only"),
    shellDescription,
  ].filter(Boolean).join(" · ");
  const emptyState = loading ? (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      {t("thread.loadingConversation")}
    </div>
  ) : (
    <div className="flex w-full flex-col items-center text-center animate-in fade-in-0 slide-in-from-bottom-2 duration-500">
      <HeroGreeting text={t(heroGreetingKey)} />
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        {isChineseLocale ? "输入问题、任务或文件需求，按 Enter 发送。" : "Type a question, task, or file request, then press Enter."}
      </p>
    </div>
  );
  const sessionInfoAction = supportsThreads && historyKey ? (
    <ExecutionInfoPopover executionKey={historyKey} token={token} title={title} />
  ) : undefined;
  const promptNavigatorAction = supportsThreads && historyKey ? (
    <PromptNavigator
      messages={displayMessages}
      onJumpToPrompt={(promptId) => viewportRef.current?.jumpToUserPrompt(promptId)}
    />
  ) : undefined;

  return (
    <section
      ref={shellRef}
      className="relative flex min-h-0 flex-1 overflow-hidden bg-[radial-gradient(circle_at_top,rgba(14,165,233,0.08),transparent_28%),linear-gradient(180deg,rgba(248,250,252,0.95)_0%,rgba(241,245,249,0.98)_100%)]"
    >
      <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden px-3 pb-3 pt-2">
        {!hideHeader ? (
          <ThreadHeader
            title={title}
            onToggleSidebar={onToggleSidebar}
            theme={theme}
            onToggleTheme={onToggleTheme}
            hideSidebarToggleForHostChrome={hideSidebarToggleForHostChrome}
            hostChromeTitleInset={hostChromeTitleInset}
            hideThemeButton={hideThemeButton}
            minimal={!session && !loading}
            subtitle={shellPosture || null}
            capabilityBadges={capabilityBadges}
            promptNavigatorAction={promptNavigatorAction}
            sessionInfoAction={sessionInfoAction}
          />
        ) : null}
        <FilePreviewAvailabilityProvider
          resolve={historyKey ? resolveFilePreviewAvailability : undefined}
        >
          {!session && !loading ? (
            <div className="relative flex min-h-0 flex-1 items-center justify-center px-4 py-8">
              <div className="w-full max-w-3xl rounded-[30px] border border-slate-200/90 bg-white/95 p-5 shadow-[0_28px_90px_rgba(15,23,42,0.12)] sm:p-7">
                <div className="mb-5 text-center">
                  {emptyState}
                </div>
                <div className="rounded-[26px] border border-slate-950/10 bg-slate-50/80 p-2 shadow-inner">
                  {composer}
                </div>
              </div>
            </div>
          ) : (
          <div className="relative min-h-0 flex-1 overflow-hidden rounded-[28px] border border-slate-200/80 bg-white/88 shadow-[0_30px_80px_rgba(15,23,42,0.08)]">
            <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-20 bg-[linear-gradient(180deg,rgba(248,250,252,0.96)_0%,rgba(248,250,252,0)_100%)]" />
            <div className="absolute inset-x-0 top-0 z-20 flex items-center justify-between border-b border-slate-200/70 px-4 py-2">
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                {isChineseLocale ? "对话" : "Conversation"}
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em]",
                    turnActive
                      ? "border-cyan-300/80 bg-cyan-50 text-cyan-700"
                      : "border-slate-300/80 bg-slate-50 text-slate-700",
                  )}
                >
                  {turnActive ? (isChineseLocale ? "回复中" : "streaming") : (isChineseLocale ? "空闲" : "idle")}
                </span>
                <span className="rounded-full border border-slate-300/80 bg-slate-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-700">
                  {historyKey ? (isChineseLocale ? "已连接" : "attached") : (isChineseLocale ? "待开始" : "standby")}
                </span>
              </div>
            </div>
            <div className="h-full pt-11">
              <ThreadViewport
                ref={viewportRef}
                messages={displayMessages}
                isStreaming={turnActive}
                emptyState={emptyState}
                composer={composer}
                activeTurnId={viewportTurnId}
                activeTurnStartedHere={activeTurnStartedHere}
                conversationKey={historyKey}
                conversationReady={messagesReady}
                showScrollToBottomButton={!!session}
                cliApps={cliApps}
                mcpPresets={mcpPresets}
                slashCommands={slashCommands}
                forkBoundaryMessageCount={forkBoundaryMessageCount}
                hasMoreBefore={hasMoreBefore}
                loadingOlder={loadingOlder}
                userMessageOffset={userMessageOffset}
                onLoadOlder={loadOlder}
                onOpenFilePreview={historyKey && supportsFileActivity ? handleOpenFilePreview : undefined}
                showFileActivity={supportsFileActivity}
                onForkFromMessage={
                  !readOnlyExecution && supportsThreads && handleForkExecution
                    ? handleForkFromMessage
                    : undefined
                }
                onQuoteSelection={activeExecution ? handleQuoteSelection : undefined}
              />
            </div>
          </div>
          )}
        </FilePreviewAvailabilityProvider>
      </div>
      {supportsFileActivity && filePreviewPath && historyKey ? (
        <FilePreviewPanel
          sessionKey={historyKey}
          path={filePreviewPath}
          token={token}
          desktopWidth={filePreviewWidth}
          isClosing={filePreviewClosing}
          onResizeStart={handleFilePreviewResizeStart}
          onClose={handleCloseFilePreview}
        />
      ) : null}
    </section>
  );
}

export const WorkbenchShell = ThreadShell;
