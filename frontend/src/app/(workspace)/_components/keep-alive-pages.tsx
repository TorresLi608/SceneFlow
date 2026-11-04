"use client";

import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";
import { Suspense, useState, type ComponentType } from "react";

import {
  KEEP_ALIVE_ROUTES,
  matchKeepAliveRoute,
  withVisitedRoute,
  type KeepAliveRoute,
} from "@/lib/keep-alive-routes";

// Dynamic imports keep each surface in its own chunk, as the route pages were, so visiting
// /usage or /admin/* never downloads the chat or generation panels.
const SURFACES: Record<KeepAliveRoute, ComponentType<{ active: boolean }>> = {
  "/chat": dynamic(() => import("../chat/_components/chat-surface").then((module) => module.ChatSurface)),
  "/images": dynamic(() => import("../images/_components/image-surface").then((module) => module.ImageSurface)),
  "/audio": dynamic(() => import("../audio/_components/audio-surface").then((module) => module.AudioSurface)),
  "/videos": dynamic(() => import("../videos/_components/video-surface").then((module) => module.VideoSurface)),
};

/**
 * Mounts request-owning controllers on first visit. Each panel places its view in Activity below
 * its query/mutation hooks: disconnecting a pending TanStack mutation observer loses its updates.
 * Leaving the workspace layout still unmounts the surfaces.
 */
export function KeepAlivePages() {
  const pathname = usePathname();
  const activeRoute = matchKeepAliveRoute(pathname);
  const [visited, setVisited] = useState<readonly KeepAliveRoute[]>(() => withVisitedRoute([], activeRoute));
  const nextVisited = withVisitedRoute(visited, activeRoute);
  if (nextVisited !== visited) {
    // First visit mounts the surface; later visits only change which slot is visible.
    setVisited(nextVisited);
  }

  return (
    <>
      {KEEP_ALIVE_ROUTES.filter((route) => nextVisited.includes(route)).map((route) => {
        const Surface = SURFACES[route];
        return (
          <Suspense key={route} fallback={null}>
            <Surface active={route === activeRoute} />
          </Suspense>
        );
      })}
    </>
  );
}
