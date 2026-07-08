"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Shield } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import {
  deleteAdminUserAction,
  listAdminUsersAction,
  updateAdminUserAction,
} from "@/actions/admin-actions";
import { queryKeys } from "@/actions/query-keys";
import { getMeAction } from "@/actions/user-actions";
import { ModelConfigManager } from "@/app/admin/_components/model-config-manager";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { resolveRequestError } from "@/lib/http/errors";
import { useUserStore } from "@/store/user-store";

export default function AdminPage() {
  const queryClient = useQueryClient();
  const hydrated = useUserStore((state) => state.hydrated);
  const token = useUserStore((state) => state.token);
  const user = useUserStore((state) => state.user);
  const setUser = useUserStore((state) => state.setUser);
  const logout = useUserStore((state) => state.logout);

  const [view, setView] = useState<"models" | "users">("models");
  const [message, setMessage] = useState<string | null>(null);

  const meQuery = useQuery({
    queryKey: queryKeys.me,
    queryFn: getMeAction,
    enabled: hydrated && Boolean(token),
  });

  const currentUser = meQuery.data?.user ?? user;
  const isSuperAdmin = currentUser?.role === "superAdmin";

  const usersQuery = useQuery({
    queryKey: queryKeys.adminUsers,
    queryFn: listAdminUsersAction,
    enabled: Boolean(isSuperAdmin),
  });

  useEffect(() => {
    if (meQuery.data?.user) {
      setUser(meQuery.data.user);
    }
  }, [meQuery.data?.user, setUser]);

  const updateUserMutation = useMutation({
    mutationFn: ({ id, isDisabled }: { id: number; isDisabled: boolean }) => updateAdminUserAction(id, { isDisabled }),
    onSuccess: async () => {
      setMessage("用户状态已更新。");
      await queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers });
    },
    onError: (error) => setMessage(resolveRequestError(error, "更新用户状态失败")),
  });

  const deleteUserMutation = useMutation({
    mutationFn: deleteAdminUserAction,
    onSuccess: async () => {
      setMessage("用户已删除。");
      await queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers });
    },
    onError: (error) => setMessage(resolveRequestError(error, "删除用户失败")),
  });

  const isMutating =
    updateUserMutation.isPending ||
    deleteUserMutation.isPending;

  const deleteUser = (id: number, username: string) => {
    if (!window.confirm(`确认删除用户「${username}」吗？`)) {
      return;
    }
    deleteUserMutation.mutate(id);
  };

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
            配置管理
          </Button>
          <Button className="mt-1 w-full justify-start" variant={view === "users" ? "default" : "ghost"} onClick={() => setView("users")}>
            用户管理
          </Button>
        </aside>

        <section className="min-w-0">
          {view === "models" ? (
            <ModelConfigManager />
          ) : (
            <Card>
            <CardHeader>
              <CardTitle>已注册用户</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {(usersQuery.data?.users ?? []).map((item) => (
                <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border/70 p-3">
                  <div>
                    <p className="text-sm font-medium">{item.username}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      ID {item.id} · {item.role} · {item.isDisabled ? "已禁用" : "正常"}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={item.role === "superAdmin" || isMutating}
                      onClick={() => updateUserMutation.mutate({ id: item.id, isDisabled: !item.isDisabled })}
                    >
                      {item.isDisabled ? "启用" : "禁用"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={item.role === "superAdmin" || isMutating}
                      onClick={() => deleteUser(item.id, item.username)}
                    >
                      删除
                    </Button>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
          )}

          {message ? <p className="mt-4 text-sm text-muted-foreground">{message}</p> : null}
        </section>
      </div>
    </main>
  );
}
