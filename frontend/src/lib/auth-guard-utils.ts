export const PUBLIC_PATHS = ["/login", "/register"];

/**
 * 判断给定路径是否属于免鉴权公开白名单。
 */
export function isPublicRoute(pathname: string): boolean {
  return PUBLIC_PATHS.includes(pathname);
}

/**
 * 构建带有原访问路径重定向参数的登录页 URL。
 */
export function buildLoginRedirectUrl(pathname: string): string {
  const redirectParam = pathname && pathname !== "/" ? `?redirect=${encodeURIComponent(pathname)}` : "";
  return `/login${redirectParam}`;
}

/**
 * 解析并校验重定向路径，严格限制为站内相对路径，防止开放重定向攻击。
 */
export function resolveSafeRedirectUrl(redirectParam: string | null | undefined, fallback = "/"): string {
  if (redirectParam && redirectParam.startsWith("/") && !redirectParam.startsWith("//")) {
    return redirectParam;
  }
  return fallback;
}
