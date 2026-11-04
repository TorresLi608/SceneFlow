"use client";

import { Activity, createContext, useContext, useEffectEvent, useLayoutEffect, useRef, type ReactNode } from "react";

const ActivityVisibilityContext = createContext(true);

/** Portaled controls must unmount while hidden: Activity only hides the view's DOM root. */
export function useActivityVisible() {
  return useContext(ActivityVisibilityContext);
}

type ViewProps = { children: ReactNode; className: string; onHide: () => void };

function VisibleView({ children, className, onHide }: ViewProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const handleHide = useEffectEvent(onHide);

  useLayoutEffect(() => {
    const root = rootRef.current;
    return () => {
      // Hiding DOM preserves playback position, but does not pause audio/video by itself.
      root?.querySelectorAll<HTMLMediaElement>("audio, video").forEach((media) => media.pause());
      handleHide();
    };
  }, []);

  return <div ref={rootRef} className={className}>{children}</div>;
}

/** Keep request-owning hooks above this boundary; only the view's effects disconnect when hidden. */
export function ActivityView({ active, ...props }: ViewProps & { active: boolean }) {
  return (
    <ActivityVisibilityContext value={active}>
      <Activity mode={active ? "visible" : "hidden"}>
        <VisibleView {...props} />
      </Activity>
    </ActivityVisibilityContext>
  );
}
