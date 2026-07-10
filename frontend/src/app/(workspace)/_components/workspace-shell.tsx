"use client";

import { useQuery } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { queryKeys } from "@/actions/query-keys";
import { getMeAction } from "@/actions/user-actions";
import { PreferencesSwitcher } from "@/components/preferences-switcher";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { useUserStore } from "@/store/user-store";

import { AppSidebar } from "./app-sidebar";

function pageTitleKey(pathname: string) {
  if (pathname.startsWith("/images")) return "home.images";
  if (pathname.startsWith("/videos")) return "home.videos";
  if (pathname.startsWith("/ai-script")) return "home.aiScript";
  if (pathname.startsWith("/admin/models")) return "home.modelManagement";
  if (pathname.startsWith("/admin/users")) return "home.userManagement";
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

  const meQuery = useQuery({
    queryKey: queryKeys.me,
    queryFn: getMeAction,
    enabled: hydrated && Boolean(token),
  });

  useEffect(() => {
    if (meQuery.data?.user) setUser(meQuery.data.user);
  }, [meQuery.data?.user, setUser]);

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
              <Button
                variant="secondary"
                onClick={() => {
                  logout();
                  router.replace("/login");
                }}
              >
                <LogOut className="mr-2 size-4" />
                {t("common.logout")}
              </Button>
            </div>
          </div>
        </header>

        {children}
      </section>
    </main>
  );
}
