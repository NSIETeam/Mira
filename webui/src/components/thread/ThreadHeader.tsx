import { Menu, Moon, Sun } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ThreadHeaderProps {
  title: string;
  onToggleSidebar?: () => void;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  hideSidebarToggleForHostChrome?: boolean;
  hostChromeTitleInset?: boolean;
  hideThemeButton?: boolean;
  minimal?: boolean;
  subtitle?: string | null;
  capabilityBadges?: string[];
  promptNavigatorAction?: ReactNode;
  sessionInfoAction?: ReactNode;
}

export function ThreadHeader({
  title,
  onToggleSidebar,
  theme,
  onToggleTheme,
  hideSidebarToggleForHostChrome = false,
  hostChromeTitleInset = false,
  hideThemeButton = false,
  minimal = false,
  subtitle = null,
  capabilityBadges = [],
  promptNavigatorAction,
  sessionInfoAction,
}: ThreadHeaderProps) {
  const { t } = useTranslation();

  return (
    <div
      className={cn(
        "relative z-10 flex items-center justify-between gap-3 px-3 py-2",
        minimal && "h-11",
        !minimal && hostChromeTitleInset && "lg:pl-[128px]",
      )}
    >
      <div className="relative flex min-w-0 items-center gap-2">
        {onToggleSidebar ? (
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("thread.header.toggleSidebar")}
            onClick={onToggleSidebar}
            className={cn(
              "h-7 w-7 rounded-md text-muted-foreground hover:bg-accent/35 hover:text-foreground",
              hideSidebarToggleForHostChrome && "lg:hidden",
            )}
          >
            <Menu className="h-3.5 w-3.5" />
          </Button>
        ) : null}
        {!minimal ? (
          <div className="flex min-w-0 items-center rounded-md px-1.5 py-1 text-[12px] font-medium text-muted-foreground">
            <span className="max-w-[min(60vw,32rem)] truncate">{title}</span>
          </div>
        ) : null}
      </div>

      <div className="ml-auto flex shrink-0 items-center gap-1">
        {!minimal && (subtitle || capabilityBadges.length > 0) ? (
          <div className="hidden items-center gap-2 pr-1 text-[11px] text-muted-foreground lg:flex">
            {subtitle ? (
              <span className="max-w-[22rem] truncate">{subtitle}</span>
            ) : null}
            {capabilityBadges.length > 0 ? (
              <div className="flex items-center gap-1">
                {capabilityBadges.map((badge) => (
                  <span
                    key={badge}
                    className="rounded-full border border-border/70 bg-muted/40 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground/90"
                  >
                    {badge}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        {sessionInfoAction}
        {promptNavigatorAction}
        {!hideThemeButton ? (
          <ThemeButton
            theme={theme}
            onToggleTheme={onToggleTheme}
            label={t("thread.header.toggleTheme")}
          />
        ) : null}
      </div>

      {!minimal ? (
        <div aria-hidden className="pointer-events-none absolute inset-x-0 top-full h-4" />
      ) : null}
    </div>
  );
}

function ThemeButton({
  theme,
  onToggleTheme,
  label,
  className,
}: {
  theme: "light" | "dark";
  onToggleTheme: () => void;
  label: string;
  className?: string;
}) {
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={label}
      onClick={onToggleTheme}
      className={cn(
        "host-no-drag h-8 w-8 rounded-full text-muted-foreground/85 hover:bg-accent/40 hover:text-foreground",
        className,
      )}
    >
      {theme === "dark" ? (
        <Sun className="h-4 w-4" />
      ) : (
        <Moon className="h-4 w-4" />
      )}
    </Button>
  );
}
