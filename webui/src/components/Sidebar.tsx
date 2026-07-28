import { useState, type ReactNode } from "react";
import {
  Archive,
  Brain,
  CalendarClock,
  Menu,
  Search,
  Settings,
  SquarePen,
  Blocks,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { ExecutionList } from "@/components/ExecutionList";
import { ConnectionBadge } from "@/components/ConnectionBadge";
import { Button } from "@/components/ui/button";
import { formatHostChromeTagline, type HostKernelStatus } from "@/shells/engineering/kernel-status";
import type {
  ExecutionSummary,
  SidebarViewState,
} from "@/lib/types";
import { cn } from "@/lib/utils";

interface SidebarProps {
  appName?: string;
  kernelStatus?: HostKernelStatus;
  sessions: ExecutionSummary[];
  executions?: ExecutionSummary[];
  activeKey?: string | null;
  activeExecutionKey?: string | null;
  loading: boolean;
  onNewExecution: () => void;
  onSelect: (key: string) => void;
  onRequestDeleteExecution: (key: string, label: string) => void;
  onRequestDelete?: (key: string, label: string) => void;
  onTogglePin: (key: string) => void;
  onRequestRename: (key: string, label: string) => void;
  onToggleArchive: (key: string) => void;
  onToggleGroup: (groupId: string) => void;
  onRequestRenameProject: (projectKey: string, label: string) => void;
  onNewExecutionInProject: (projectPath: string, projectName: string) => void;
  onOpenSettings: () => void;
  onOpenApps: () => void;
  onOpenSkills: () => void;
  onOpenAutomations: () => void;
  onSettingsIntent?: () => void;
  onOpenSearch: () => void;
  activeUtility?: "apps" | "skills" | "automations" | null;
  onToggleArchived: () => void;
  onCollapse: () => void;
  onExpand?: () => void;
  containActionMenus?: boolean;
  collapsed?: boolean;
  pinnedKeys?: string[];
  archivedKeys?: string[];
  titleOverrides?: Record<string, string>;
  projectNameOverrides?: Record<string, string>;
  collapsedGroups?: Record<string, boolean>;
  runningExecutionIds?: string[];
  updatedExecutionIds?: string[];
  viewState?: SidebarViewState;
  showArchived?: boolean;
  archivedCount?: number;
  defaultWorkspacePath?: string | null;
  hostChromeInset?: boolean;
}

type NavigatorWithUserAgentData = Navigator & {
  userAgentData?: { platform?: string };
};

function isApplePlatform(): boolean {
  if (typeof navigator === "undefined") return false;
  const platform = navigator.platform || "";
  const userAgentPlatform =
    (navigator as NavigatorWithUserAgentData).userAgentData?.platform || "";
  return /mac|iphone|ipad|ipod/i.test(`${platform} ${userAgentPlatform}`);
}

function newExecutionShortcutLabel(): string {
  return isApplePlatform() ? "⌘⇧O" : "Ctrl+Shift+O";
}

export function Sidebar(props: SidebarProps) {
  const { t } = useTranslation();
  const [menuPortalContainer, setMenuPortalContainer] =
    useState<HTMLElement | null>(null);
  const collapsed = Boolean(props.collapsed);
  const toggleLabel = t("thread.header.toggleSidebar");
  const newChatShortcut = newExecutionShortcutLabel();
  const executionItems = props.executions ?? props.sessions;
  const resolvedActiveKey = props.activeExecutionKey ?? props.activeKey ?? null;
  const runningExecutionIds = props.runningExecutionIds;
  const updatedExecutionIds = props.updatedExecutionIds;
  const appName = props.appName ?? "Mira";
  const appTagline = props.kernelStatus
    ? formatHostChromeTagline(appName, props.kernelStatus)
    : "Execution kernel";

  return (
    <nav
      ref={props.containActionMenus ? setMenuPortalContainer : undefined}
      aria-label={t("sidebar.navigation")}
      className={cn(
        "flex h-full w-full min-w-0 flex-col border-r border-slate-200/70 text-sidebar-foreground",
        props.hostChromeInset
          ? "bg-[linear-gradient(180deg,rgba(255,255,255,0.58)_0%,rgba(248,250,252,0.82)_100%)] backdrop-blur-xl"
          : "bg-[linear-gradient(180deg,rgba(255,255,255,0.96)_0%,rgba(248,250,252,0.98)_100%)]",
      )}
    >
      <div
        className={cn(
          "flex items-center px-3 pb-2.5",
          props.hostChromeInset ? "pt-[2.85rem]" : "pt-3",
          collapsed ? "w-14 justify-start" : "justify-between",
        )}
      >
        <button
          type="button"
          aria-label={collapsed ? toggleLabel : undefined}
          aria-hidden={collapsed ? undefined : true}
          title={collapsed ? toggleLabel : undefined}
          onClick={collapsed ? props.onExpand : undefined}
          tabIndex={collapsed ? 0 : -1}
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-xl transition-colors",
            collapsed
              ? "-ml-0.5 hover:bg-sidebar-accent/75"
              : "pointer-events-none -ml-0.5",
          )}
        >
          <img
            src="/brand/mira_mark.svg"
            alt=""
            className="h-8 w-8 select-none object-contain"
            draggable={false}
          />
        </button>
        {!collapsed && (
          <div className="ml-2 min-w-0 flex-1">
            <div className="truncate text-[15px] font-semibold tracking-[-0.01em] text-sidebar-foreground">
              {appName}
            </div>
            <div className="truncate text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
              {appTagline}
            </div>
          </div>
        )}
        {!collapsed && !props.hostChromeInset && (
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("sidebar.collapse")}
            onClick={props.onCollapse}
            className="h-7 w-7 rounded-lg text-muted-foreground/85 hover:bg-sidebar-accent/75 hover:text-sidebar-foreground"
          >
            <Menu className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>

      <div
        className={cn(
          "space-y-1.5 border-b border-slate-200/70 px-2 pb-3",
          collapsed && "flex w-14 flex-col items-center px-0",
        )}
      >
        {!collapsed ? (
          <div className="px-2 pb-1 pt-0.5 text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Workbench
          </div>
        ) : null}
        <SidebarActionButton
          collapsed={collapsed}
          label={t("sidebar.newChat")}
          onClick={props.onNewExecution}
          icon={<SquarePen className="h-4 w-4" />}
          shortcut={newChatShortcut}
          ariaKeyShortcuts="Meta+Shift+O Control+Shift+O"
        />
        <SidebarActionButton
          collapsed={collapsed}
          label={t("sidebar.searchAria")}
          onClick={props.onOpenSearch}
          icon={<Search className="h-4 w-4" />}
        />
        <SidebarActionButton
          collapsed={collapsed}
          label={t("sidebar.apps")}
          onClick={props.onOpenApps}
          onIntent={props.onSettingsIntent}
          active={props.activeUtility === "apps"}
          icon={<Blocks className="h-4 w-4" />}
        />
        <SidebarActionButton
          collapsed={collapsed}
          label={t("sidebar.skills.title")}
          onClick={props.onOpenSkills}
          onIntent={props.onSettingsIntent}
          active={props.activeUtility === "skills"}
          icon={<Brain className="h-4 w-4" />}
        />
        <SidebarActionButton
          collapsed={collapsed}
          label={t("sidebar.automations", { defaultValue: "Automations" })}
          onClick={props.onOpenAutomations}
          onIntent={props.onSettingsIntent}
          active={props.activeUtility === "automations"}
          icon={<CalendarClock className="h-4 w-4" />}
        />
        {props.archivedCount ? (
          <SidebarActionButton
            collapsed={collapsed}
            label={props.showArchived ? t("chat.hideArchived") : t("chat.showArchived")}
            onClick={props.onToggleArchived}
            icon={<Archive className="h-4 w-4" />}
          />
        ) : null}
      </div>
      <div
        className={cn(
          "flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden transition-opacity duration-200",
          collapsed && "pointer-events-none opacity-0",
        )}
      >
        {!collapsed && (
          <ExecutionList
            sessions={executionItems}
            executions={executionItems}
            activeExecutionKey={resolvedActiveKey}
            loading={props.loading}
            emptyLabel={t("chat.noSessions")}
            onSelect={props.onSelect}
            onRequestDelete={props.onRequestDeleteExecution}
            onRequestDeleteExecution={props.onRequestDeleteExecution}
            onTogglePin={props.onTogglePin}
            onRequestRename={props.onRequestRename}
            onToggleArchive={props.onToggleArchive}
            onToggleGroup={props.onToggleGroup}
            onRequestRenameProject={props.onRequestRenameProject}
            onNewExecutionInProject={props.onNewExecutionInProject}
            pinnedKeys={props.pinnedKeys}
            archivedKeys={props.archivedKeys}
            titleOverrides={props.titleOverrides}
            projectNameOverrides={props.projectNameOverrides}
            collapsedGroups={props.collapsedGroups}
            runningExecutionIds={runningExecutionIds}
            updatedExecutionIds={updatedExecutionIds}
            density={props.viewState?.density}
            showPreviews={props.viewState?.show_previews}
            showTimestamps={props.viewState?.show_timestamps}
            sort={props.viewState?.sort}
            showArchived={props.showArchived}
            defaultWorkspacePath={props.defaultWorkspacePath}
            actionMenuPortalContainer={
              props.containActionMenus ? menuPortalContainer : undefined
            }
          />
        )}
      </div>
      <div
        className={cn(
          "flex items-center gap-1 bg-sidebar/55 px-2.5 py-3 text-xs",
          collapsed && "w-14 flex-col px-0",
        )}
      >
        <SidebarActionButton
          collapsed={collapsed}
          label={t("sidebar.settings")}
          onClick={props.onOpenSettings}
          onIntent={props.onSettingsIntent}
          className={collapsed ? undefined : "flex-1"}
          icon={<Settings className="h-4 w-4" />}
        />
        <ConnectionBadge />
      </div>
    </nav>
  );
}

export const WorkbenchSidebar = Sidebar;

function SidebarActionButton({
  collapsed,
  label,
  icon,
  onClick,
  active = false,
  className,
  shortcut,
  ariaKeyShortcuts,
  onIntent,
}: {
  collapsed: boolean;
  label: string;
  icon: ReactNode;
  onClick: () => void;
  active?: boolean;
  className?: string;
  shortcut?: string;
  ariaKeyShortcuts?: string;
  onIntent?: () => void;
}) {
  const title = shortcut ? `${label} (${shortcut})` : collapsed ? label : undefined;

  return (
    <Button
      type="button"
      variant="ghost"
      aria-label={label}
      aria-current={active ? "page" : undefined}
      aria-keyshortcuts={ariaKeyShortcuts}
      title={title}
      onClick={() => onClick()}
      onFocus={onIntent}
      onPointerEnter={onIntent}
      className={cn(
        "touch-target group h-8 min-w-0 gap-2 overflow-hidden rounded-full font-medium text-sidebar-foreground/85 hover:bg-sidebar-accent/75 hover:text-sidebar-foreground",
        "transition-[width,padding,border-radius,color,background-color] duration-300 ease-out",
        collapsed
          ? "w-9 justify-center gap-0 rounded-xl px-0"
          : "w-full justify-start gap-2 px-3 text-[12.5px]",
        active && "bg-sidebar-accent text-sidebar-foreground shadow-[inset_0_0_0_1px_hsl(var(--sidebar-border)/0.55)]",
        className,
      )}
    >
      <span
        className={cn(
          "flex shrink-0 items-center justify-center transition-transform duration-300 ease-out",
          collapsed ? "translate-x-0" : "translate-x-0",
        )}
        aria-hidden
      >
        {icon}
      </span>
      <span
        className={cn(
          "min-w-0 overflow-hidden truncate whitespace-nowrap transition-[max-width,opacity,transform] duration-200 ease-out",
          collapsed
            ? "max-w-0 -translate-x-1 opacity-0"
            : "max-w-[12rem] translate-x-0 opacity-100",
        )}
      >
        {label}
      </span>
    </Button>
  );
}
