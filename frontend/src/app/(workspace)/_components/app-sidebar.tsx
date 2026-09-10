"use client";

import {
  Activity,
  AudioLines,
  BadgeDollarSign,
  Clapperboard,
  Compass,
  History,
  ImageIcon,
  KeyRound,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Shield,
  SlidersHorizontal,
  Sparkles,
  TriangleAlert,
  Video,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentType, ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { usePreferencesStore } from "@/store/preferences-store";

function SidebarLink({
  href,
  active,
  icon: Icon,
  badge,
  collapsed,
  onNavigate,
  children,
}: {
  href: string;
  active: boolean;
  icon: ComponentType<{ className?: string }>;
  badge?: string;
  collapsed: boolean;
  onNavigate?: () => void;
  children: ReactNode;
}) {
  const link = (
    <Link
      href={href}
      onNavigate={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group relative flex items-center rounded-xl text-left text-sm font-medium transition-all duration-150 cursor-pointer",
        collapsed
          ? "size-10 justify-center mx-auto"
          : "w-full gap-2.5 px-3 py-2.5",
        active
          ? "bg-primary/10 text-primary shadow-xs dark:bg-primary/15"
          : "text-muted-foreground hover:bg-muted/70 hover:text-foreground"
      )}
    >
      {/* 激活指示光条 */}
      {active ? (
        <span
          className={cn(
            "absolute left-0 top-1/2 -translate-y-1/2 rounded-r-full bg-primary shadow-[0_0_8px_rgba(59,130,246,0.8)]",
            collapsed ? "h-6 w-1" : "h-5 w-1"
          )}
        />
      ) : null}

      <Icon
        className={cn(
          "size-4 shrink-0 transition-colors",
          active ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
        )}
      />

      <span className={cn("truncate", collapsed && "sr-only")}>{children}</span>
      {!collapsed && badge ? (
        <span className="ml-auto rounded-full bg-primary/20 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
          {badge}
        </span>
      ) : null}
    </Link>
  );

  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger render={link} />
        <TooltipContent side="right" sideOffset={12}>
          <div className="flex items-center gap-1.5 font-medium">
            <span>{children}</span>
            {badge ? (
              <span className="rounded-full bg-primary/20 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
                {badge}
              </span>
            ) : null}
          </div>
        </TooltipContent>
      </Tooltip>
    );
  }

  return link;
}

export function AppSidebar({
  showUserManagement,
  className,
  onNavigate,
  isMobile = false,
}: {
  showUserManagement: boolean;
  className?: string;
  onNavigate?: () => void;
  isMobile?: boolean;
}) {
  const pathname = usePathname();
  const { t } = useI18n();
  const preferencesCollapsed = usePreferencesStore((state) => state.sidebarCollapsed);
  const toggleSidebarCollapsed = usePreferencesStore((state) => state.toggleSidebarCollapsed);
  const collapsed = isMobile ? false : preferencesCollapsed;

  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <aside
      className={cn(
        "relative flex min-h-0 shrink-0 flex-col border-r border-border/70 bg-sidebar/70 backdrop-blur-xl transition-[width] duration-300 ease-in-out",
        collapsed ? "w-[68px]" : "w-[260px]",
        className
      )}
    >
      {/* 品牌 Logo 区域与唯一的折叠/展开切换按钮 */}
      <div
        className={cn(
          "border-b border-border/60 transition-all duration-300",
          collapsed
            ? "flex flex-col items-center justify-center gap-2 p-3"
            : "flex items-center justify-between gap-3 p-4"
        )}
      >
        <div className={cn("flex items-center gap-3 min-w-0", collapsed && "justify-center")}>
          <div className="relative flex size-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-primary via-blue-500 to-cyan-400 text-primary-foreground shadow-md shadow-primary/20">
            <Sparkles className="size-5" />
            <span className="absolute -bottom-0.5 -right-0.5 size-2 rounded-full bg-emerald-400 ring-2 ring-background" />
          </div>
          {!collapsed ? (
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-bold tracking-tight text-foreground">SceneFlow</span>
              </div>
              <p className="truncate text-[11px] text-muted-foreground">
                {t("home.brandSubtitle")}
              </p>
            </div>
          ) : null}
        </div>

        {!isMobile ? (
          <Tooltip>
            <TooltipTrigger
              render={<Button
                variant="ghost"
                size="icon"
                onClick={toggleSidebarCollapsed}
                className={cn(
                  "shrink-0 text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer",
                  collapsed ? "size-8 rounded-lg" : "size-8"
                )}
                aria-label={collapsed ? t("home.expandSidebar") : t("home.collapseSidebar")}
              />}
            >
              {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
            </TooltipTrigger>
            <TooltipContent side="right" sideOffset={12}>
              <span>{collapsed ? t("home.expandSidebar") : t("home.collapseSidebar")}</span>
            </TooltipContent>
          </Tooltip>
        ) : null}
      </div>

      {/* 导航列表 */}
      <div className="flex-1 overflow-y-auto px-2.5 py-3 chat-message-list-scrollbar">
        <nav className="flex flex-col gap-1" aria-label={t("home.menu")}>
          {/* 多模态生成矩阵 */}
          <div className="pb-1">
            {collapsed ? (
              <div className="my-2 h-px w-7 mx-auto bg-border/60" />
            ) : (
              <p className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
                {t("home.businessCenter")}
              </p>
            )}
            <div className="mt-1 space-y-0.5">
              <SidebarLink
                onNavigate={onNavigate}
                href="/chat"
                active={isActive("/chat")}
                icon={MessageSquare}
                collapsed={collapsed}
              >
                {t("home.chat")}
              </SidebarLink>
              <SidebarLink
                onNavigate={onNavigate}
                href="/images"
                active={isActive("/images")}
                icon={ImageIcon}
                collapsed={collapsed}
              >
                {t("home.images")}
              </SidebarLink>
              <SidebarLink
                onNavigate={onNavigate}
                href="/audio"
                active={isActive("/audio")}
                icon={AudioLines}
                collapsed={collapsed}
              >
                {t("home.audioGeneration")}
              </SidebarLink>
              <SidebarLink
                onNavigate={onNavigate}
                href="/videos"
                active={isActive("/videos")}
                icon={Video}
                collapsed={collapsed}
              >
                {t("home.videos")}
              </SidebarLink>
              <SidebarLink
                onNavigate={onNavigate}
                href="/ai-script"
                active={isActive("/ai-script")}
                icon={Clapperboard}
                badge="PRO"
                collapsed={collapsed}
              >
                {t("home.aiScript")}
              </SidebarLink>
            </div>
          </div>

          {/* 个人中心 */}
          <div className="pt-2">
            {collapsed ? (
              <div className="my-2 h-px w-7 mx-auto bg-border/60" />
            ) : (
              <p className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
                {t("home.personalCenter")}
              </p>
            )}
            <div className="mt-1 space-y-0.5">
              <SidebarLink
                onNavigate={onNavigate}
                href="/profile"
                active={isActive("/profile")}
                icon={Settings}
                collapsed={collapsed}
              >
                {t("home.personalSettings")}
              </SidebarLink>
              <SidebarLink
                onNavigate={onNavigate}
                href="/usage"
                active={isActive("/usage")}
                icon={Activity}
                collapsed={collapsed}
              >
                {t("home.usageLogs")}
              </SidebarLink>
            </div>
          </div>

          {/* 管理中心 */}
          <div className="pt-2">
            {collapsed ? (
              <div className="my-2 h-px w-7 mx-auto bg-border/60" />
            ) : (
              <p className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
                {t("home.adminCenter")}
              </p>
            )}
            <div className="mt-1 space-y-0.5">
              <SidebarLink
                onNavigate={onNavigate}
                href="/admin/models"
                active={isActive("/admin/models")}
                icon={SlidersHorizontal}
                collapsed={collapsed}
              >
                {t("home.modelManagement")}
              </SidebarLink>
              {showUserManagement ? (
                <>
                  <SidebarLink
                    onNavigate={onNavigate}
                    href="/admin/users"
                    active={isActive("/admin/users")}
                    icon={Shield}
                    collapsed={collapsed}
                  >
                    {t("home.userManagement")}
                  </SidebarLink>
                  <SidebarLink
                    onNavigate={onNavigate}
                    href="/admin/usage-logs"
                    active={isActive("/admin/usage-logs")}
                    icon={History}
                    collapsed={collapsed}
                  >
                    {t("home.allUsageRecords")}
                  </SidebarLink>
                  <SidebarLink
                    onNavigate={onNavigate}
                    href="/admin/error-logs"
                    active={isActive("/admin/error-logs")}
                    icon={TriangleAlert}
                    collapsed={collapsed}
                  >
                    {t("home.errorLogs")}
                  </SidebarLink>
                  <SidebarLink
                    onNavigate={onNavigate}
                    href="/admin/invitation-codes"
                    active={isActive("/admin/invitation-codes")}
                    icon={KeyRound}
                    collapsed={collapsed}
                  >
                    {t("home.invitationCodeManagement")}
                  </SidebarLink>
                  <SidebarLink
                    onNavigate={onNavigate}
                    href="/admin/redemption-codes"
                    active={isActive("/admin/redemption-codes")}
                    icon={BadgeDollarSign}
                    collapsed={collapsed}
                  >
                    {t("home.redemptionCodeManagement")}
                  </SidebarLink>
                </>
              ) : null}
            </div>
          </div>
        </nav>
      </div>

      {/* 底部快捷提示 */}
      <div className="border-t border-border/60 p-2.5">
        {!collapsed ? (
          <div className="flex items-center gap-2 rounded-xl bg-card/60 p-2.5 ring-1 ring-border/70 backdrop-blur-md">
            <Compass className="size-4 text-primary shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-foreground">{t("home.aiEngineTitle")}</p>
              <p className="truncate text-[10px] text-muted-foreground">{t("home.aiEngineSubtitle")}</p>
            </div>
          </div>
        ) : (
          <div className="flex justify-center py-1">
            <Tooltip>
              <TooltipTrigger render={<div />}>
                <div className="flex size-9 items-center justify-center rounded-xl bg-card/60 text-primary ring-1 ring-border/70 backdrop-blur-md">
                  <Compass className="size-4" />
                </div>
              </TooltipTrigger>
              <TooltipContent side="right" sideOffset={12}>
                <p className="text-xs font-medium">{t("home.aiEngineTitle")}</p>
              </TooltipContent>
            </Tooltip>
          </div>
        )}
      </div>
    </aside>
  );
}
