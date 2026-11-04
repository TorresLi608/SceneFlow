/**
 * Workspace routes whose page controller stays mounted (its view is hidden by React Activity) after the
 * first visit. Next.js unmounts a page on every navigation, which would discard an in-flight
 * image/video/voice generation or a streaming chat answer; the workspace shell therefore hosts
 * these surfaces itself and the route's `page.tsx` only claims the URL.
 */
export const KEEP_ALIVE_ROUTES = ["/chat", "/images", "/audio", "/videos"] as const;

export type KeepAliveRoute = (typeof KEEP_ALIVE_ROUTES)[number];

export function matchKeepAliveRoute(pathname: string): KeepAliveRoute | null {
  return KEEP_ALIVE_ROUTES.find((route) => pathname === route || pathname.startsWith(`${route}/`)) ?? null;
}

/** Returns the same array when nothing changes so callers can compare by reference. */
export function withVisitedRoute(
  visited: readonly KeepAliveRoute[],
  route: KeepAliveRoute | null
): readonly KeepAliveRoute[] {
  if (!route || visited.includes(route)) {
    return visited;
  }
  return [...visited, route];
}
