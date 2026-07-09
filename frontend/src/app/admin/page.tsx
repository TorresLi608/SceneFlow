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
import { useUserStore } from "@/store/user-store";

export default function AdminPage() {
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
    return <main className="min-h-screen bg-background p-6 text-sm text-muted-foreground">加载中...</main>;
  }

  if (!token) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background p-6">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle>需要登录</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>请使用 superAdmin 账号登录后进入管理后台。</p>
            <Button render={<Link href="/login" />}>去登录</Button>
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
            <CardTitle>无权限</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>当前账号不是 superAdmin。</p>
            <div className="flex gap-2">
              <Button variant="outline" render={<Link href="/" />}>返回工作台</Button>
              <Button
                variant="secondary"
                onClick={() => {
                  logout();
                  window.location.href = "/login";
                }}
              >
                退出登录
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
              返回工作台
            </Link>
            <h1 className="mt-2 flex items-center gap-2 text-xl font-semibold">
              <Shield className="size-5" />
              SceneFlow 管理后台
            </h1>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl gap-4 p-4 md:grid-cols-[220px_minmax(0,1fr)] md:p-6">
        <aside className="h-fit rounded-lg border border-border/70 bg-muted/20 p-2">
          <Button className="w-full justify-start" variant={view === "models" ? "default" : "ghost"} onClick={() => setView("models")}>
            模型管理
          </Button>
          <Button className="mt-1 w-full justify-start" variant={view === "users" ? "default" : "ghost"} onClick={() => setView("users")}>
            用户管理
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
