"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, LogOut, Settings, UserRound } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { queryKeys } from "@/actions/query-keys";
import { getMeAction } from "@/actions/user-actions";
import { PreferencesSwitcher } from "@/components/preferences-switcher";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverDescription, PopoverHeader, PopoverTitle, PopoverTrigger } from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";
import { useI18n } from "@/lib/i18n";
import { useUserStore } from "@/store/user-store";

import { AppSidebar } from "./app-sidebar";

function pageTitleKey(pathname: string) {
  if (pathname.startsWith("/images")) return "home.images";
  if (pathname.startsWith("/videos")) return "home.videos";
  if (pathname.startsWith("/usage")) return "home.usageLogs";
  if (pathname.startsWith("/profile")) return "home.personalSettings";
  if (pathname.startsWith("/ai-script")) return "home.aiScript";
  if (pathname.startsWith("/admin/models")) return "home.modelManagement";
  if (pathname.startsWith("/admin/users")) return "home.userManagement";
  if (pathname.startsWith("/admin/usage-logs")) return "home.allUsageRecords";
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
    return <main className="flex min-h-screen items-center justify-center">{t("common.initializing")}</main>;
  }

  if (!token || meQuery.isError) {
    return <main className="flex min-h-screen items-center justify-center">{t("common.redirectingToLogin")}</main>;
  }

  return (
    <main className="flex h-screen overflow-hidden bg-background text-foreground">
      <AppSidebar showUserManagement={user?.role === "superAdmin"} />

      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="border-b border-border/70 bg-card/60">
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 md:px-6">
            <div>
              <p className="text-base font-semibold">{t(pageTitleKey(pathname))}</p>
              <p className="text-xs text-muted-foreground">
                {t("common.currentUser", {
                  username: meQuery.isLoading ? t("common.loading") : user?.username ?? t("common.unknownUser"),
                })}
              </p>
            </div>

            <div className="flex items-center gap-2">
              <PreferencesSwitcher />
              <Popover open={accountOpen} onOpenChange={setAccountOpen}>
                <div onMouseEnter={keepAccountOpen} onMouseLeave={scheduleAccountClose}>
                  <PopoverTrigger render={<Button variant="secondary" />}>
                    <UserRound data-icon="inline-start" />
                    {user?.username ?? t("common.loading")}
                    <ChevronDown data-icon="inline-end" />
                  </PopoverTrigger>
                </div>
                <PopoverContent align="end" onMouseEnter={keepAccountOpen} onMouseLeave={scheduleAccountClose}>
                  <PopoverHeader>
                    <PopoverTitle>{user?.username ?? t("common.unknownUser")}</PopoverTitle>
                    <PopoverDescription>{t("admin.levelValue", { level: user?.level ?? 1 })}</PopoverDescription>
                  </PopoverHeader>
                  <Separator />
                  <div className="flex flex-col gap-1">
                    <Button variant="ghost" className="justify-start" onClick={() => { setAccountOpen(false); router.push("/profile"); }}>
                      <Settings data-icon="inline-start" />
                      {t("home.personalSettings")}
                    </Button>
                    <Button
                      variant="ghost"
                      className="justify-start"
                      onClick={() => {
                        setAccountOpen(false);
                        logout();
                        router.replace("/login");
                      }}
                    >
                      <LogOut data-icon="inline-start" />
                      {t("common.logout")}
                    </Button>
                  </div>
                </PopoverContent>
              </Popover>
            </div>
          </div>
        </header>

        {children}
      </section>
    </main>
  );
}
