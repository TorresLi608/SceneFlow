"use client";

import { ExternalLink } from "lucide-react";
import Image from "next/image";

import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export interface MediaPreviewItem {
  kind: "image" | "video";
  url: string;
  title: string;
}

export function MediaPreviewDialog({
  item,
  onOpenChange,
}: {
  item: MediaPreviewItem | null;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useI18n();

  return (
    <Dialog open={Boolean(item)} onOpenChange={onOpenChange}>
      <DialogContent className="w-[98vw] max-w-[1850px] h-[95dvh] max-h-[96dvh] flex flex-col p-0 overflow-hidden gap-0 rounded-2xl border border-border/80 shadow-2xl bg-background">
        <DialogHeader className="p-3 pr-12 border-b border-border/70 flex flex-row flex-wrap items-center justify-between gap-2 sm:pl-5 bg-card/40 shrink-0">
          <DialogTitle className="min-w-0 max-w-full truncate text-sm font-bold">{item?.title}</DialogTitle>
          {item?.url ? (
            <div className="flex shrink-0 items-center gap-2">
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                title={t("common.openInNewTab")}
                className={cn(
                  buttonVariants({ variant: "ghost", size: "xs" }),
                  "gap-1 text-xs text-muted-foreground hover:text-foreground inline-flex items-center"
                )}
              >
                <ExternalLink className="size-3" />
                {t("common.openInNewTab")}
              </a>
            </div>
          ) : null}
        </DialogHeader>
        {item ? (
          <div className="relative flex flex-1 min-h-0 items-center justify-center overflow-hidden bg-black/95 dark:bg-black p-2 sm:p-4">
            <div className="pointer-events-none absolute inset-0 bg-grid-dots opacity-10" />
            {item.kind === "image" ? (
              <div className="relative h-full w-full flex items-center justify-center">
                <Image
                  src={item.url}
                  alt={item.title}
                  fill
                  unoptimized
                  sizes="100vw"
                  className="object-contain drop-shadow-2xl select-none"
                />
              </div>
            ) : (
              <video
                src={item.url}
                controls
                autoPlay
                loop
                className="max-h-full max-w-full rounded-2xl shadow-2xl object-contain border border-white/10"
              />
            )}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
