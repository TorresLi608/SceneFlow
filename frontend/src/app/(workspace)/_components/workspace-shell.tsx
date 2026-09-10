"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ChevronDown,
  Crown,
  LogOut,
  Menu,
  Settings,
  UserRound,
} from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { queryKeys } from "@/actions/query-keys";
import { getMeAction } from "@/actions/user-actions";
import { PreferencesSwitcher } from "@/components/preferences-switcher";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";
import { useI18n } from "@/lib/i18n";
import { useUserStore } from "@/store/user-store";

import { AppSidebar } from "./app-sidebar";

function pageTitleKey(pathname: string) {
  if (pathname.startsWith("/images")) return "home.images";
  if (pathname.startsWith("/audio")) return "home.audioGeneration";
  if (pathname.startsWith("/videos")) return "home.videos";
  if (pathname.startsWith("/usage")) return "home.usageLogs";
  if (pathname.startsWith("/profile")) return "home.personalSettings";
  if (pathname.startsWith("/ai-script")) return "home.aiScript";
  if (pathname.startsWith("/admin/models")) return "home.modelManagement";
  if (pathname.startsWith("/admin/users")) return "home.userManagement";
  if (pathname.startsWith("/admin/usage-logs")) return "home.allUsageRecords";
  if (pathname.startsWith("/admin/error-logs")) return "home.errorLogs";
  if (pathname.startsWith("/admin/invitation-codes")) return "home.invitationCodeManagement";
  if (pathname.startsWith("/admin/redemption-codes")) return "home.redemptionCodeManagement";
  return "home.chat";
}

export function WorkspaceShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { t } = useI18n();
  const hydrated = useUserStore((state) => state.hydrated);
  const token = useUserStore((state) => state.token);
  const user = useUserStore((state) => state.user);
  const setUser = useUserStore((state) => state.setUser);
  const logout = useUserStore((state) => state.logout);
  const [accountOpen, setAccountOpen] = useState(false);
  const [navigationPath, setNavigationPath] = useState<string | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const keepAccountOpen = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    setAccountOpen(true);
  };
  const scheduleAccountClose = () => {
    closeTimer.current = setTimeout(() => setAccountOpen(false), 160);
  };

  const meQuery = useQuery({
    queryKey: queryKeys.me,
    queryFn: getMeAction,
    enabled: hydrated && Boolean(token),
  });

  useEffect(() => {
    if (meQuery.data?.user) setUser(meQuery.data.user);
  }, [meQuery.data?.user, setUser]);

  useEffect(() => () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    if (!token) {
      router.replace("/login");
      return;
    }
    if (meQuery.isError) {
      logout();
      router.replace("/login");
    }
  }, [hydrated, token, meQuery.isError, logout, router]);

  if (!hydrated) {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-background">
        <div className="flex items-center gap-3 rounded-2xl border border-border/70 bg-card/60 px-5 py-3 shadow-xl backdrop-blur-md">
          <span className="size-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <span className="text-sm font-medium text-muted-foreground">{t("common.initializing")}</span>
        </div>
      </main>
    );
  }

  if (!token || meQuery.isError) {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-background">
        <div className="flex items-center gap-3 rounded-2xl border border-border/70 bg-card/60 px-5 py-3 shadow-xl backdrop-blur-md">
          <span className="size-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <span className="text-sm font-medium text-muted-foreground">{t("common.redirectingToLogin")}</span>
        </div>
      </main>
    );
  }

  const isSuperAdmin = user?.role === "superAdmin";

  return (
    <main className="safe-area flex h-dvh overflow-hidden bg-background text-foreground">
      <AppSidebar showUserManagement={isSuperAdmin} className="hidden lg:flex" />

      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        {/* 顶部毛玻璃导航栏 */}
        <header className="shrink-0 border-b border-border/70 bg-card/40 backdrop-blur-xl">
          <div className="flex items-center justify-between gap-2 px-3 py-2 sm:px-4 sm:py-3 md:px-6">
            <div className="flex min-w-0 items-center gap-2 sm:gap-3">
              <Dialog open={navigationPath === pathname} onOpenChange={(open) => setNavigationPath(open ? pathname : null)}>
                <DialogTrigger render={<Button variant="outline" size="icon" className="shrink-0 lg:hidden" aria-label={t("home.menu")} />}>
                  <Menu />
                </DialogTrigger>
                <DialogContent className="top-[env(safe-area-inset-top)] left-[env(safe-area-inset-left)] h-[calc(100dvh-env(safe-area-inset-top)-env(safe-area-inset-bottom))] max-h-dvh w-72 max-w-[calc(100%-3rem)] translate-x-0 translate-y-0 gap-0 rounded-none p-0 sm:max-w-xs" aria-describedby={undefined}>
                  <DialogTitle className="sr-only">{t("home.menu")}</DialogTitle>
                  <AppSidebar isMobile showUserManagement={isSuperAdmin} className="h-full w-full border-0 [&>div:first-child]:pr-12" onNavigate={() => setNavigationPath(null)} />
                </DialogContent>
              </Dialog>
              <div className="min-w-0">
                <h1 className="truncate text-sm font-bold tracking-tight text-foreground sm:text-lg">
                  {t(pageTitleKey(pathname))}
                </h1>
                <p className="hidden truncate text-[11px] text-muted-foreground sm:block">
                  {t("common.currentUser", {
                    username: meQuery.isLoading
                      ? t("common.loading")
                      : user?.nickname || user?.username || t("common.unknownUser"),
                  })}
                </p>
              </div>
            </div>

            <div className="flex shrink-0 items-center gap-1.5 sm:gap-2.5">
              <PreferencesSwitcher />

              {/* 用户快捷菜单 */}
              <Popover open={accountOpen} onOpenChange={setAccountOpen}>
                <div onMouseEnter={keepAccountOpen} onMouseLeave={scheduleAccountClose}>
                  <PopoverTrigger
                    render={
                      <Button
                        variant="outline"
                        className="h-9 gap-2 rounded-xl border-border/80 bg-card/60 px-2 backdrop-blur-md hover:bg-card hover:border-primary/40 cursor-pointer shadow-xs sm:px-3"
                        aria-label={t("home.personalSettings")}
                      />
                    }
                  >
                    <div className="flex size-6 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      {isSuperAdmin ? <Crown className="size-3.5" /> : <UserRound className="size-3.5" />}
                    </div>
                    <span className="hidden max-w-[160px] truncate text-xs font-semibold sm:inline">
                      {user?.nickname || user?.username || t("common.loading")}
                    </span>
                    <ChevronDown className="hidden size-3.5 text-muted-foreground sm:block" />
                  </PopoverTrigger>
                </div>

                <PopoverContent
                  align="end"
                  className="w-56 gap-1 rounded-xl border-border/80 bg-card/95 p-1.5 shadow-2xl backdrop-blur-xl dark:border-white/10"
                  onMouseEnter={keepAccountOpen}
                  onMouseLeave={scheduleAccountClose}
                >
                  {/* 用户信息头部卡片 */}
                  <div className="flex items-center gap-2.5 rounded-lg border border-border/40 bg-muted/40 p-2">
                    <div className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-primary font-bold text-xs shadow-2xs">
                      {isSuperAdmin ? <Crown className="size-4" /> : <UserRound className="size-4" />}
                    </div>
                    <div className="flex min-w-0 flex-1 flex-col justify-center">
                      <div className="flex items-center justify-between gap-1.5">
                        <span className="truncate text-xs font-semibold text-foreground">
                          {user?.nickname || user?.username || t("common.unknownUser")}
                        </span>
                        {isSuperAdmin ? (
                          <Badge variant="default" className="h-4 px-1.5 text-[9px] font-bold uppercase shrink-0">
                            Admin
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="h-4 px-1.5 text-[10px] shrink-0">
                            Lv.{user?.level ?? 1}
                          </Badge>
                        )}
                      </div>
                      <span className="truncate text-[11px] text-muted-foreground">
                        @{user?.username}
                      </span>
                    </div>
                  </div>

                  {/* 快捷菜单项列表 */}
                  <div className="flex flex-col gap-0.5 pt-0.5">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 justify-start gap-2.5 rounded-md px-2.5 text-xs font-normal text-foreground/90 hover:bg-accent/80 hover:text-foreground focus-visible:bg-accent focus-visible:outline-none focus-visible:ring-0 cursor-pointer transition-colors"
                      onClick={() => {
                        setAccountOpen(false);
                        router.push("/profile");
                      }}
                    >
                      <Settings className="size-3.5 text-muted-foreground" />
                      {t("home.personalSettings")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 justify-start gap-2.5 rounded-md px-2.5 text-xs font-normal text-foreground/90 hover:bg-accent/80 hover:text-foreground focus-visible:bg-accent focus-visible:outline-none focus-visible:ring-0 cursor-pointer transition-colors"
                      onClick={() => {
                        setAccountOpen(false);
                        router.push("/usage");
                      }}
                    >
                      <Activity className="size-3.5 text-muted-foreground" />
                      {t("home.usageLogs")}
                    </Button>
                  </div>

                  <Separator className="my-0.5 bg-border/50" />

                  {/* 退出登录 */}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 justify-start gap-2.5 rounded-md px-2.5 text-xs font-normal text-rose-500 hover:bg-rose-500/10 hover:text-rose-600 focus-visible:bg-rose-500/10 focus-visible:outline-none focus-visible:ring-0 cursor-pointer transition-colors dark:text-rose-400 dark:hover:bg-rose-500/15 dark:hover:text-rose-300"
                    onClick={() => {
                      setAccountOpen(false);
                      logout();
                      router.replace("/login");
                    }}
                  >
                    <LogOut className="size-3.5" />
                    {t("common.logout")}
                  </Button>
                </PopoverContent>
              </Popover>
            </div>
          </div>
        </header>

        {/* 页面内容注入 */}
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</div>
      </section>
    </main>
  );
}
