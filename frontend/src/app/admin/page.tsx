"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Shield } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { queryKeys } from "@/actions/query-keys";
import { getMeAction } from "@/actions/user-actions";
import { AdminUsersManager } from "@/app/admin/_components/admin-users-manager";
import { ModelConfigManager } from "@/app/admin/_components/model-config-manager";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useI18n } from "@/lib/i18n";
import { useUserStore } from "@/store/user-store";

export default function AdminPage() {
  const { t } = useI18n();
  const hydrated = useUserStore((state) => state.hydrated);
  const token = useUserStore((state) => state.token);
  const user = useUserStore((state) => state.user);
  const setUser = useUserStore((state) => state.setUser);
  const logout = useUserStore((state) => state.logout);

  const [view, setView] = useState<"models" | "users">("models");

  const meQuery = useQuery({
    queryKey: queryKeys.me,
    queryFn: getMeAction,
    enabled: hydrated && Boolean(token),
  });

  const currentUser = meQuery.data?.user ?? user;
  const isSuperAdmin = currentUser?.role === "superAdmin";

  useEffect(() => {
    if (meQuery.data?.user) {
      setUser(meQuery.data.user);
    }
  }, [meQuery.data?.user, setUser]);

  if (!hydrated || meQuery.isLoading) {
    return <main className="min-h-screen bg-background p-6 text-sm text-muted-foreground">{t("admin.loading")}</main>;
  }

  if (!token) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background p-6">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle>{t("admin.loginRequired")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>{t("admin.loginRequiredDescription")}</p>
            <Button render={<Link href="/login" />}>{t("admin.goLogin")}</Button>
          </CardContent>
        </Card>
      </main>
    );
  }

  if (!isSuperAdmin) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background p-6">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle>{t("admin.forbidden")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>{t("admin.forbiddenDescription")}</p>
            <div className="flex gap-2">
              <Button variant="outline" render={<Link href="/" />}>{t("admin.backToWorkspace")}</Button>
              <Button
                variant="secondary"
                onClick={() => {
                  logout();
                  window.location.href = "/login";
                }}
              >
                {t("common.logout")}
              </Button>
            </div>
          </CardContent>
        </Card>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background">
      <header className="border-b border-border/70 px-4 py-4 md:px-6">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
          <div>
            <Link href="/" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
              <ArrowLeft className="size-3.5" />
              {t("admin.backToWorkspace")}
            </Link>
            <h1 className="mt-2 flex items-center gap-2 text-xl font-semibold">
              <Shield className="size-5" />
              {t("admin.title")}
            </h1>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl gap-4 p-4 md:grid-cols-[220px_minmax(0,1fr)] md:p-6">
        <aside className="h-fit rounded-lg border border-border/70 bg-muted/20 p-2">
          <Button className="w-full justify-start" variant={view === "models" ? "default" : "ghost"} onClick={() => setView("models")}>
            {t("home.modelManagement")}
          </Button>
          <Button className="mt-1 w-full justify-start" variant={view === "users" ? "default" : "ghost"} onClick={() => setView("users")}>
            {t("home.userManagement")}
          </Button>
        </aside>

        <section className="min-w-0">
          {view === "models" ? (
            <ModelConfigManager />
          ) : (
            <AdminUsersManager />
          )}
        </section>
      </div>
    </main>
  );
}
