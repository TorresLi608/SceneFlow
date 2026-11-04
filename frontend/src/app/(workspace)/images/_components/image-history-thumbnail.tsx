"use client";

import { ImageIcon } from "lucide-react";
import Image from "next/image";
import { useEffect, useRef, useState, type RefObject } from "react";

import { artifactBffUrl } from "@/lib/artifact-url";

export function ImageHistoryThumbnail({
  url,
  active,
  scrollRootRef,
}: {
  url: string | null | undefined;
  active: boolean;
  scrollRootRef: RefObject<HTMLDivElement | null>;
}) {
  const elementRef = useRef<HTMLSpanElement>(null);
  const [visible, setVisible] = useState(false);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);

  useEffect(() => {
    const element = elementRef.current;
    const root = scrollRootRef.current;
    if (!active || !url || !element || !root) return;
    let connected = true;
    const observer = new IntersectionObserver((entries) => {
      if (connected) {
        setVisible(entries.some((entry) => entry.isIntersecting));
      }
    }, { root, rootMargin: "80px 0px" });
    observer.observe(element);
    return () => {
      connected = false;
      observer.disconnect();
    };
  }, [active, url, scrollRootRef]);

  return (
    <span ref={elementRef} className="relative size-11 shrink-0 overflow-hidden rounded-lg bg-muted border border-border/50">
      {active && visible && url && failedUrl !== url ? (
        <Image
          src={artifactBffUrl(url)}
          alt=""
          fill
          unoptimized
          sizes="44px"
          loading="eager"
          fetchPriority="low"
          className="object-cover"
          onError={() => setFailedUrl(url)}
        />
      ) : (
        <ImageIcon className="absolute inset-0 m-auto size-4 text-muted-foreground" />
      )}
    </span>
  );
}
