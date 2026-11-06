"use client";

import { ImageIcon, LoaderCircle } from "lucide-react";
import Image from "next/image";
import { useState } from "react";

import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export function ImageResultPreview({ src, alt, sizes }: { src: string; alt: string; sizes: string }) {
  const { t } = useI18n();
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  return (
    <div className="relative flex h-full w-full items-center justify-center" aria-busy={status === "loading"}>
      <Image
        src={src}
        alt={alt}
        fill
        unoptimized
        loading="eager"
        sizes={sizes}
        onLoad={() => setStatus("ready")}
        onError={() => setStatus("error")}
        className={cn("object-contain drop-shadow-2xl", status !== "ready" && "invisible")}
      />
      {status === "loading" ? (
        <div role="status" className="flex items-center gap-2 rounded-xl bg-background/90 px-4 py-3 text-sm text-muted-foreground">
          <LoaderCircle className="size-4 animate-spin" aria-hidden />
          {t("images.previewLoading")}
        </div>
      ) : status === "error" ? (
        <div role="alert" className="flex items-center gap-2 rounded-xl bg-background/90 px-4 py-3 text-sm text-muted-foreground">
          <ImageIcon className="size-4" aria-hidden />
          {t("images.previewLoadFailed")}
        </div>
      ) : null}
    </div>
  );
}
