import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { PanelLeft, ShieldCheck, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { channelUiPresentation } from "@/channel-plugins/registry";
import { Button } from "@/components/ui/button";
import { useLogoFallback } from "@/hooks/useLogoFallback";
import { logoFallbackUrls } from "@/lib/provider-brand";
import type { PairingRequestInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

export function SurfaceLoadingFallback() {
  return (
    <div
      aria-busy="true"
      className="flex h-full w-full flex-col gap-5 px-5 py-8 sm:px-8 lg:px-12"
    >
      <span className="sr-only">Loading</span>
      <div className="h-4 w-20 animate-pulse rounded bg-muted/70 motion-reduce:animate-none" />
      <div className="h-9 w-48 animate-pulse rounded bg-muted/70 motion-reduce:animate-none" />
      <div className="mt-4 h-12 w-full max-w-3xl animate-pulse rounded-md bg-muted/55 motion-reduce:animate-none" />
      <div className="h-28 w-full max-w-3xl animate-pulse rounded-md bg-muted/40 motion-reduce:animate-none" />
    </div>
  );
}

export function HostChrome({
  onToggleSidebar,
  onSidebarPreviewEnter,
  onSidebarPreviewLeave,
  sidebarOpen = true,
  rightAction,
  appName = "Mira",
  appTagline = "Kernel workbench",
}: {
  onToggleSidebar?: () => void;
  onSidebarPreviewEnter?: () => void;
  onSidebarPreviewLeave?: () => void;
  sidebarOpen?: boolean;
  rightAction?: ReactNode;
  appName?: string;
  appTagline?: string;
}) {
  const { t } = useTranslation();
  const healthBadge = appTagline.includes("· offline")
    ? { label: "offline", className: "border-slate-400/80 bg-slate-100 text-slate-700" }
    : appTagline.endsWith("· attention")
    ? { label: "attention", className: "border-rose-300/80 bg-rose-50 text-rose-700" }
    : appTagline.includes("· healthy")
      ? { label: "healthy", className: "border-emerald-300/80 bg-emerald-50 text-emerald-700" }
      : null;
  const maintenanceBadge = appTagline.endsWith("· maintenance")
    ? { label: "maintenance", className: "border-amber-300/80 bg-amber-50 text-amber-700" }
    : appTagline.endsWith("· live")
      ? { label: "live", className: "border-slate-300/80 bg-slate-50 text-slate-700" }
      : null;
  const healthDotClass = maintenanceBadge?.label === "maintenance"
    ? "bg-amber-500 shadow-[0_0_0_3px_rgba(245,158,11,0.18)]"
    : healthBadge?.label === "offline"
      ? "bg-slate-500 shadow-[0_0_0_3px_rgba(100,116,139,0.18)]"
    : healthBadge?.label === "attention"
      ? "bg-rose-500 shadow-[0_0_0_3px_rgba(244,63,94,0.18)]"
      : "bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.16)]";
  const chromeCapsuleClass = maintenanceBadge?.label === "maintenance"
    ? "border-amber-200/90 bg-amber-50/90 text-amber-800"
    : healthBadge?.label === "offline"
      ? "border-slate-300/90 bg-slate-100/95 text-slate-700"
    : healthBadge?.label === "attention"
      ? "border-rose-200/90 bg-rose-50/90 text-rose-800"
      : "border-slate-200/70 bg-white/75 text-slate-500";
  const chromeCapsuleMotionClass = maintenanceBadge?.label === "maintenance"
    ? "shadow-[0_0_0_1px_rgba(245,158,11,0.10),0_10px_28px_rgba(245,158,11,0.12)]"
    : healthBadge?.label === "offline"
      ? "shadow-[0_0_0_1px_rgba(100,116,139,0.10),0_10px_24px_rgba(100,116,139,0.12)]"
    : healthBadge?.label === "attention"
      ? "shadow-[0_0_0_1px_rgba(244,63,94,0.10),0_10px_28px_rgba(244,63,94,0.14)] animate-pulse"
      : "shadow-sm";
  const privilegeBadge = appTagline.includes("· root")
    ? { label: "root", className: "border-emerald-300/80 bg-emerald-50 text-emerald-700" }
    : appTagline.includes("· user")
      ? { label: "user", className: "border-amber-300/80 bg-amber-50 text-amber-700" }
      : null;
  const visibleTagline = privilegeBadge || healthBadge || maintenanceBadge
    ? appTagline.replace(/\s*·\s*(root|user)\s*/g, " · ").replace(/\s*·\s*(healthy|attention|offline)\s*/g, " · ").replace(/\s*·\s*(maintenance|live)\s*$/, "").replace(/\s*·\s*$/, "")
    : appTagline;
  const chromeStatusTitle = [
    privilegeBadge ? `privilege ${privilegeBadge.label}` : null,
    healthBadge ? `kernel ${healthBadge.label}` : null,
    maintenanceBadge ? `runtime ${maintenanceBadge.label}` : null,
  ].filter(Boolean).join(" · ");
  const chromeStatusLabel = [
    healthBadge?.label,
    maintenanceBadge?.label === "maintenance" ? "maintenance" : null,
  ].filter(Boolean).join(" / ");
  const runtimeState =
    maintenanceBadge?.label === "maintenance"
      ? "maintenance"
      : healthBadge?.label === "offline"
        ? "offline"
        : healthBadge?.label === "attention"
          ? "attention"
          : "healthy";

  return (
    <header className="host-drag-region pointer-events-none absolute inset-x-0 top-0 z-40 h-12 border-b border-slate-200/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.94)_0%,rgba(248,250,252,0.84)_100%)] text-foreground/90 backdrop-blur-xl">
      {onToggleSidebar ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={t("thread.header.toggleSidebar")}
          data-testid="host-sidebar-toggle"
          onClick={onToggleSidebar}
          onFocus={!sidebarOpen ? onSidebarPreviewEnter : undefined}
          onBlur={!sidebarOpen ? onSidebarPreviewLeave : undefined}
          onMouseEnter={!sidebarOpen ? onSidebarPreviewEnter : undefined}
          onMouseLeave={!sidebarOpen ? onSidebarPreviewLeave : undefined}
          className="host-no-drag pointer-events-auto absolute left-[84px] top-[9px] h-7 w-7 rounded-lg border border-slate-200/70 bg-white/80 text-muted-foreground shadow-sm hover:bg-white hover:text-foreground"
        >
          <PanelLeft className="h-[15px] w-[15px]" strokeWidth={1.75} />
        </Button>
      ) : null}
      <div className="pointer-events-none absolute inset-x-0 top-0 flex h-12 items-center justify-center">
        <div
          className={cn(
            "flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-medium uppercase tracking-[0.18em] transition-colors motion-reduce:animate-none",
            chromeCapsuleClass,
            chromeCapsuleMotionClass,
          )}
          role="status"
          aria-live="polite"
          aria-atomic="true"
          aria-label={chromeStatusTitle || `${appName} kernel status`}
          data-kernel-health={healthBadge?.label ?? "unknown"}
          data-kernel-connected={healthBadge?.label === "offline" ? "false" : "true"}
          data-runtime-maintenance={maintenanceBadge?.label ?? "unknown"}
          data-shell-privilege={privilegeBadge?.label ?? "unknown"}
          data-runtime-state={runtimeState}
          data-kernel-status-summary={chromeStatusTitle || undefined}
          title={chromeStatusTitle || undefined}
        >
          {chromeStatusTitle ? <span className="sr-only">{chromeStatusTitle}</span> : null}
          <span className="text-slate-900">{appName}</span>
          <span className={cn("h-1.5 w-1.5 rounded-full", healthDotClass)} />
          <span>{visibleTagline}</span>
          {chromeStatusLabel ? (
            <span className="rounded-full border border-current/15 bg-black/[0.03] px-2 py-0.5 text-[10px] font-semibold tracking-[0.14em]">
              {chromeStatusLabel}
            </span>
          ) : null}
          {privilegeBadge ? (
            <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-semibold tracking-[0.14em]", privilegeBadge.className)}>
              {privilegeBadge.label}
            </span>
          ) : null}
          {healthBadge ? (
            <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-semibold tracking-[0.14em]", healthBadge.className)}>
              {healthBadge.label}
            </span>
          ) : null}
          {maintenanceBadge ? (
            <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-semibold tracking-[0.14em]", maintenanceBadge.className)}>
              {maintenanceBadge.label}
            </span>
          ) : null}
        </div>
      </div>
      {rightAction ? (
        <div className="host-no-drag pointer-events-auto absolute right-3 top-2 rounded-full border border-slate-200/70 bg-white/80 p-1 shadow-sm">
          {rightAction}
        </div>
      ) : null}
    </header>
  );
}

export function PairingCodePopup({
  requests,
  total,
  busyCode,
  error,
  onApprove,
  onDismiss,
}: {
  requests: PairingRequestInfo[];
  total: number;
  busyCode: string | null;
  error: string | null;
  onApprove: (code: string) => void;
  onDismiss: (code: string) => void;
}) {
  const { t } = useTranslation();
  const [value, setValue] = useState("");
  const normalizedCode = normalizePairingCode(value);
  const matchedRequest = useMemo(
    () => requests.find((request) => request.code === normalizedCode) ?? null,
    [normalizedCode, requests],
  );
  const firstRequest = requests[0] ?? null;
  const displayRequest = matchedRequest ?? firstRequest;
  const expires = formatPairingExpiry(firstRequest?.expires_in_seconds);
  const isCompleteCode = normalizedCode.length === 9;
  const showNoMatch = isCompleteCode && !matchedRequest && !busyCode;

  useEffect(() => {
    if (!matchedRequest || busyCode) return;
    onApprove(matchedRequest.code);
  }, [busyCode, matchedRequest, onApprove]);

  useEffect(() => {
    if (!requests.length) setValue("");
  }, [requests.length]);

  if (!firstRequest) return null;

  return (
    <div
      role="dialog"
      aria-live="polite"
      aria-label={t("app.pairing.title", { defaultValue: "Pair an execution user" })}
      className={cn(
        "fixed right-4 top-[calc(0.75rem+env(safe-area-inset-top))] z-[70]",
        "w-[min(calc(100vw-2rem),24rem)] rounded-[24px]",
        "border border-border/70 bg-popover/95 p-4 text-popover-foreground",
        "shadow-[0_24px_70px_rgba(15,23,42,0.20)] backdrop-blur-xl",
        "animate-in fade-in-0 slide-in-from-top-2 duration-200",
      )}
    >
      <div className="flex items-start gap-3">
        <PairingChannelBadge channel={displayRequest.channel} />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[15px] font-semibold tracking-[-0.01em]">
                {t("app.pairing.title", { defaultValue: "Pair an execution user" })}
              </p>
              <p className="mt-1 text-[13px] leading-5 text-muted-foreground">
                {t("app.pairing.description", {
                  defaultValue: "Enter the pairing code shown in the execution channel.",
                })}
              </p>
            </div>
            <button
              type="button"
              aria-label={t("common.close", { defaultValue: "Close" })}
              onClick={() => onDismiss(firstRequest.code)}
              className="rounded-full p-1 text-muted-foreground transition hover:bg-muted hover:text-foreground"
            >
              <X className="h-4 w-4" aria-hidden />
            </button>
          </div>

          <label className="mt-4 block text-[12.5px] font-medium text-foreground">
            {t("app.pairing.code", { defaultValue: "Pairing code" })}
          </label>
          <PairingCodeSlots
            value={value}
            disabled={Boolean(busyCode)}
            matched={Boolean(matchedRequest)}
            invalid={showNoMatch}
            ariaLabel={t("app.pairing.code", { defaultValue: "Pairing code" })}
            onChange={(next) => setValue(formatPairingCodeInput(next))}
          />

          <div className="mt-3 flex items-center justify-between gap-3 text-[12.5px] text-muted-foreground">
            <span>
              {matchedRequest
                ? t("app.pairing.matched", {
                    defaultValue: "Matched {{channel}}. Connecting...",
                    channel: channelLabel(matchedRequest.channel),
                  })
                : t("app.pairing.expiresInline", {
                    defaultValue: "Code expires {{expires}}.",
                    expires,
                  })}
            </span>
            {total > 1 ? (
              <span className="shrink-0">
                {t("app.pairing.queueCount", {
                  defaultValue: "{{count}} pending",
                  count: total,
                })}
              </span>
            ) : null}
          </div>

          {showNoMatch ? (
            <p className="mt-2 text-[12px] leading-5 text-destructive">
              {t("app.pairing.noMatch", {
                defaultValue: "No pending request matches this code.",
              })}
            </p>
          ) : null}

          {error ? (
            <p className="mt-2 text-[12px] leading-5 text-destructive">{error}</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function PairingChannelBadge({ channel }: { channel: string }) {
  const presentation = pairingChannelPresentation(channel);
  const initials = presentation.initials;
  const color = presentation.color;
  const logoUrls = useMemo(
    () => logoFallbackUrls(presentation?.logoUrl),
    [presentation?.logoUrl],
  );
  const { logoUrl, onLogoError, onLogoLoad } = useLogoFallback(logoUrls);

  return (
    <div
      className="mt-0.5 grid h-10 w-10 shrink-0 place-items-center overflow-hidden rounded-2xl border bg-background shadow-sm"
      style={{
        borderColor: `${color}30`,
        boxShadow: `inset 0 0 0 1px ${color}14, 0 1px 2px rgba(15,23,42,0.06)`,
      }}
      aria-hidden
    >
      {logoUrl ? (
        <img
          src={logoUrl}
          alt=""
          decoding="async"
          loading="lazy"
          className="h-6 w-6 object-contain"
          onLoad={onLogoLoad}
          onError={onLogoError}
        />
      ) : presentation ? (
        <span className="text-[11px] font-bold tracking-[-0.02em]" style={{ color }}>
          {initials}
        </span>
      ) : (
        <ShieldCheck className="h-5 w-5" style={{ color }} />
      )}
    </div>
  );
}

function PairingCodeSlots({
  value,
  disabled,
  matched,
  invalid,
  ariaLabel,
  onChange,
}: {
  value: string;
  disabled: boolean;
  matched: boolean;
  invalid: boolean;
  ariaLabel: string;
  onChange: (value: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [focused, setFocused] = useState(false);
  const compact = compactPairingCode(value);
  const activeIndex = Math.min(compact.length, 7);
  const slots = Array.from({ length: 8 }, (_, index) => compact[index] ?? "");
  const renderSlot = (char: string, index: number) => {
    const highlighted = focused && index === activeIndex && !matched && !invalid;
    return (
      <div
        key={index}
        className={cn(
          "grid h-10 w-7 place-items-center rounded-xl border",
          "bg-background/80 font-mono text-[16px] font-semibold uppercase",
          "text-foreground shadow-[0_1px_1px_rgba(15,23,42,0.04)] transition",
          matched
            ? "border-emerald-500/45 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
            : invalid
              ? "border-destructive/55 bg-destructive/5 text-destructive"
              : highlighted
                ? "border-foreground/30 bg-background text-foreground"
                : char
                  ? "border-border/80 bg-background text-foreground"
                  : "border-border/55 bg-muted/35 text-muted-foreground",
        )}
      >
        {char || " "}
      </div>
    );
  };

  return (
    <div
      className={cn(
        "relative mt-2 rounded-2xl border border-transparent p-1",
        "transition duration-150",
        focused && !disabled ? "border-ring/20 bg-muted/35" : "bg-transparent",
      )}
      onClick={() => inputRef.current?.focus()}
    >
      <input
        ref={inputRef}
        value={value}
        aria-label={ariaLabel}
        inputMode="text"
        autoCapitalize="characters"
        autoComplete="off"
        autoCorrect="off"
        spellCheck={false}
        maxLength={9}
        disabled={disabled}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onChange={(event) => onChange(event.target.value)}
        className="absolute inset-0 z-10 h-full w-full cursor-text opacity-0 disabled:cursor-default"
      />
      <div className="pointer-events-none flex items-center gap-1.5">
        {slots.slice(0, 4).map((char, index) => renderSlot(char, index))}
        <div className="mx-0.5 h-px w-2.5 rounded-full bg-muted-foreground/35" />
        {slots.slice(4).map((char, index) => renderSlot(char, index + 4))}
      </div>
    </div>
  );
}

function compactPairingCode(raw: string): string {
  return raw.replace(/[^a-zA-Z0-9]/g, "").slice(0, 8).toUpperCase();
}

function formatPairingCodeInput(raw: string): string {
  const compact = compactPairingCode(raw);
  if (compact.length <= 4) return compact;
  return `${compact.slice(0, 4)}-${compact.slice(4)}`;
}

function normalizePairingCode(raw: string): string {
  return formatPairingCodeInput(raw);
}

function pairingChannelKey(channel: string): string {
  const raw = channel.trim().toLowerCase();
  if (!raw) return "";
  return raw.split(/[.:]/)[0] ?? raw;
}

function channelLabel(channel: string): string {
  return pairingChannelPresentation(channel).label;
}

function pairingChannelPresentation(channel: string) {
  const key = pairingChannelKey(channel);
  const plugin = channelUiPresentation(key);
  return {
    label: plugin?.displayName ?? channel,
    initials: plugin?.initials ?? channel.slice(0, 2).toUpperCase(),
    color: plugin?.color ?? "#10B981",
    logoUrl: plugin?.logoUrl,
  };
}

function formatPairingExpiry(seconds: number | null | undefined): string {
  if (seconds == null) return "soon";
  if (seconds <= 0) return "expired";
  if (seconds < 60) return `${seconds}s`;
  return `${Math.ceil(seconds / 60)} min`;
}
