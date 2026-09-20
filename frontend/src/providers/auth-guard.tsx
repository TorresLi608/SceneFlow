"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { queryKeys } from "@/actions/query-keys";
import { getMeAction } from "@/actions/user-actions";
import { useI18n } from "@/lib/i18n";
import { useUserStore } from "@/store/user-store";

import {
  buildLoginRedirectUrl,
  isPublicRoute,
  PUBLIC_PATHS,
  resolveSafeRedirectUrl,
} from "@/lib/auth-guard-utils";

export { buildLoginRedirectUrl, isPublicRoute, PUBLIC_PATHS, resolveSafeRedirectUrl };

/**
 * 全局统一鉴权守卫。
 * 集中负责：
 * 1. 拦截所有受保护路由（非公开白名单路由）的未登录访问，并跳转至 /login；
 * 2. 携带当前访问路径作为 redirect 查询参数，登录后可精准回跳；
 * 3. 统一校验 Token 有效性，在 Token 过期或失效时清理状态并跳转；
 * 4. 水合与重定向期间显示统一的初始化/跳转中 Loading，防止未授权组件挂载与接口 401 报错。
 */
export function AuthGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { t } = useI18n();

  const hydrated = useUserStore((state) => state.hydrated);
  const token = useUserStore((state) => state.token);
  const setUser = useUserStore((state) => state.setUser);
  const logout = useUserStore((state) => state.logout);

  const isPublic = isPublicRoute(pathname);

  const meQuery = useQuery({
    queryKey: queryKeys.me,
    queryFn: getMeAction,
    enabled: hydrated && Boolean(token) && !isPublic,
  });

  useEffect(() => {
    if (meQuery.data?.user) {
      setUser(meQuery.data.user);
    }
  }, [meQuery.data?.user, setUser]);

  useEffect(() => {
    if (isPublic) return;
    if (!hydrated) return;

    if (!token) {
      router.replace(buildLoginRedirectUrl(pathname));
      return;
    }

    if (meQuery.isError) {
      logout();
      router.replace(buildLoginRedirectUrl(pathname));
    }
  }, [isPublic, hydrated, token, meQuery.isError, logout, pathname, router]);

  // 公开页面直接放行渲染
  if (isPublic) {
    return <>{children}</>;
  }

  // 状态水合中
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

  // 未登录或 token 校验失败正在跳转登录
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

  return <>{children}</>;
}
