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

import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

function SidebarLink({
  href,
  active,
  icon: Icon,
  badge,
  children,
}: {
  href: string;
  active: boolean;
  icon: ComponentType<{ className?: string }>;
  badge?: string;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group relative flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-sm font-medium transition-all duration-150 cursor-pointer",
        active
          ? "bg-primary/10 text-primary shadow-xs dark:bg-primary/15"
          : "text-muted-foreground hover:bg-muted/70 hover:text-foreground"
      )}
    >
      {/* 激活指示光条 */}
      {active ? (
        <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-primary shadow-[0_0_8px_rgba(59,130,246,0.8)]" />
      ) : null}

      <Icon
        className={cn(
          "size-4 shrink-0 transition-colors",
          active ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
        )}
      />
      <span className="truncate">{children}</span>

      {badge ? (
        <span className="ml-auto rounded-full bg-primary/20 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
          {badge}
        </span>
      ) : null}
    </Link>
  );
}

export function AppSidebar({ showUserManagement }: { showUserManagement: boolean }) {
  const pathname = usePathname();
  const { t } = useI18n();
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <aside className="flex w-[260px] shrink-0 flex-col border-r border-border/70 bg-sidebar/70 backdrop-blur-xl">
      {/* 品牌 Logo 区域 */}
      <div className="flex items-center gap-3 border-b border-border/60 p-4">
        <div className="relative flex size-9 items-center justify-center rounded-xl bg-gradient-to-tr from-primary via-blue-500 to-cyan-400 text-primary-foreground shadow-md shadow-primary/20">
          <Sparkles className="size-5" />
          <span className="absolute -bottom-0.5 -right-0.5 size-2 rounded-full bg-emerald-400 ring-2 ring-background" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-bold tracking-tight text-foreground">SceneFlow</span>
          </div>
          <p className="truncate text-[11px] text-muted-foreground">
            {t("home.brandSubtitle")}
          </p>
        </div>
      </div>

      {/* 导航列表 */}
      <div className="flex-1 overflow-y-auto px-3 py-3 chat-message-list-scrollbar">
        <nav className="flex flex-col gap-1" aria-label={t("home.menu")}>
          {/* 多模态生成矩阵 */}
          <div className="pb-1">
            <p className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
              {t("home.businessCenter")}
            </p>
            <div className="mt-1 space-y-0.5">
              <SidebarLink href="/chat" active={isActive("/chat")} icon={MessageSquare}>
                {t("home.chat")}
              </SidebarLink>
              <SidebarLink href="/images" active={isActive("/images")} icon={ImageIcon}>
                {t("home.images")}
              </SidebarLink>
              <SidebarLink href="/audio" active={isActive("/audio")} icon={AudioLines}>
                {t("home.audioGeneration")}
              </SidebarLink>
              <SidebarLink href="/videos" active={isActive("/videos")} icon={Video}>
                {t("home.videos")}
              </SidebarLink>
              <SidebarLink
                href="/ai-script"
                active={isActive("/ai-script")}
                icon={Clapperboard}
                badge="PRO"
              >
                {t("home.aiScript")}
              </SidebarLink>
            </div>
          </div>

          {/* 个人中心 */}
          <div className="pt-3">
            <p className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
              {t("home.personalCenter")}
            </p>
            <div className="mt-1 space-y-0.5">
              <SidebarLink href="/profile" active={isActive("/profile")} icon={Settings}>
                {t("home.personalSettings")}
              </SidebarLink>
              <SidebarLink href="/usage" active={isActive("/usage")} icon={Activity}>
                {t("home.usageLogs")}
              </SidebarLink>
            </div>
          </div>

          {/* 管理中心 */}
          <div className="pt-3">
            <p className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
              {t("home.adminCenter")}
            </p>
            <div className="mt-1 space-y-0.5">
              <SidebarLink
                href="/admin/models"
                active={isActive("/admin/models")}
                icon={SlidersHorizontal}
              >
                {t("home.modelManagement")}
              </SidebarLink>
              {showUserManagement ? (
                <>
                  <SidebarLink
                    href="/admin/users"
                    active={isActive("/admin/users")}
                    icon={Shield}
                  >
                    {t("home.userManagement")}
                  </SidebarLink>
                  <SidebarLink
                    href="/admin/usage-logs"
                    active={isActive("/admin/usage-logs")}
                    icon={History}
                  >
                    {t("home.allUsageRecords")}
                  </SidebarLink>
                  <SidebarLink
                    href="/admin/error-logs"
                    active={isActive("/admin/error-logs")}
                    icon={TriangleAlert}
                  >
                    {t("home.errorLogs")}
                  </SidebarLink>
                  <SidebarLink
                    href="/admin/invitation-codes"
                    active={isActive("/admin/invitation-codes")}
                    icon={KeyRound}
                  >
                    {t("home.invitationCodeManagement")}
                  </SidebarLink>
                  <SidebarLink
                    href="/admin/redemption-codes"
                    active={isActive("/admin/redemption-codes")}
                    icon={BadgeDollarSign}
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
      <div className="border-t border-border/60 p-3">
        <div className="flex items-center gap-2 rounded-xl bg-card/60 p-2.5 ring-1 ring-border/70 backdrop-blur-md">
          <Compass className="size-4 text-primary" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium text-foreground">{t("home.aiEngineTitle")}</p>
            <p className="truncate text-[10px] text-muted-foreground">{t("home.aiEngineSubtitle")}</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
