"use client";

import Image from "next/image";

import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export function MediaPreviewDialog({
  item,
  onOpenChange,
}: {
  item: { kind: "image" | "video"; url: string; title: string } | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={Boolean(item)} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[95vh] max-w-6xl overflow-hidden p-3 sm:p-5">
        <DialogHeader>
          <DialogTitle className="truncate pr-8 text-sm">{item?.title}</DialogTitle>
        </DialogHeader>
        {item ? (
          <div className="flex max-h-[78vh] min-h-0 items-center justify-center overflow-auto rounded-lg bg-black/80 p-2">
            {item.kind === "image" ? (
              <Image
                src={item.url}
                alt={item.title}
                width={2400}
                height={1600}
                unoptimized
                className="h-auto max-h-[74vh] w-auto max-w-full object-contain"
              />
            ) : (
              <video src={item.url} controls autoPlay className="max-h-[74vh] max-w-full rounded object-contain" />
            )}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
