import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * 仅限超级管理员访问的路由前缀列表。
 * /admin/models 对所有已登录用户开放，因此不在此名单中。
 */
const SUPER_ADMIN_ROUTES = [
  "/admin/users",
  "/admin/usage-logs",
  "/admin/error-logs",
  "/admin/invitation-codes",
  "/admin/redemption-codes",
  "/admin/generation-retention",
];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const isRestrictedAdminRoute = SUPER_ADMIN_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`)
  );

  if (isRestrictedAdminRoute) {
    const role = request.cookies.get("sceneflow-role")?.value;

    // 非超级管理员访问敏感管理后台，直接重写渲染 404 页面
    if (role !== "superAdmin") {
      const notFoundUrl = new URL("/404", request.url);
      return NextResponse.rewrite(notFoundUrl, { status: 404 });
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/admin/:path*"],
};

