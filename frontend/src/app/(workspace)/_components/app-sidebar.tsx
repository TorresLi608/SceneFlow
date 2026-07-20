"use client";

import { Activity, ImageIcon, KeyRound, LayoutDashboard, MessageSquare, Shield, SlidersHorizontal, Video } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

function SidebarLink({ href, active, children }: { href: string; active: boolean; children: ReactNode }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm",
        active ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60"
      )}
    >
      {children}
    </Link>
  );
}

export function AppSidebar({ showUserManagement }: { showUserManagement: boolean }) {
  const pathname = usePathname();
  const { t } = useI18n();
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <aside className="flex w-[248px] shrink-0 flex-col border-r border-border/70 bg-card/50">
      <div className="p-4">
        <p className="text-sm font-semibold">SceneFlow</p>
        <p className="mt-1 text-xs text-muted-foreground">{t("home.brandSubtitle")}</p>
      </div>

      <nav className="space-y-1 px-3" aria-label={t("home.menu")}>
        <p className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("home.businessCenter")}</p>
        <SidebarLink href="/chat" active={isActive("/chat")}>
          <MessageSquare className="size-4" />
          {t("home.chat")}
        </SidebarLink>
        <SidebarLink href="/images" active={isActive("/images")}>
          <ImageIcon className="size-4" />
          {t("home.images")}
        </SidebarLink>
        <SidebarLink href="/videos" active={isActive("/videos")}>
          <Video className="size-4" />
          {t("home.videos")}
        </SidebarLink>
        <SidebarLink href="/ai-script" active={isActive("/ai-script")}>
          <LayoutDashboard className="size-4" />
          {t("home.aiScript")}
        </SidebarLink>

        <div className="pt-4">
          <p className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("home.personalCenter")}</p>
          <SidebarLink href="/usage" active={isActive("/usage")}>
            <Activity className="size-4" />
            {t("home.usageLogs")}
          </SidebarLink>
        </div>

        <div className="pt-4">
          <p className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("home.adminCenter")}</p>
          <SidebarLink href="/admin/models" active={isActive("/admin/models")}>
            <SlidersHorizontal className="size-4" />
            {t("home.modelManagement")}
          </SidebarLink>
          {showUserManagement ? (
            <>
              <SidebarLink href="/admin/users" active={isActive("/admin/users")}>
                <Shield className="size-4" />
                {t("home.userManagement")}
              </SidebarLink>
              <SidebarLink href="/admin/invitation-codes" active={isActive("/admin/invitation-codes")}>
                <KeyRound className="size-4" />
                {t("home.invitationCodeManagement")}
              </SidebarLink>
            </>
          ) : null}
        </div>
      </nav>
    </aside>
  );
}
