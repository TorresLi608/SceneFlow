"use client";

import { Check, Film, ImageIcon, Loader2, Trash2, Volume2, X } from "lucide-react";
import Image from "next/image";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { GenerationReferenceInput } from "@/types/project";
import { MediaPreviewDialog } from "./media-preview-dialog";

export type ReferenceMedia = "image" | "video" | "audio";

export interface ReferenceAssetOption extends GenerationReferenceInput {
  label: string;
  media: ReferenceMedia;
  url: string;
}

const keyOf = (item: GenerationReferenceInput) => `${item.kind}:${item.id}`;

export function ReferencePicker({
  title,
  hint,
  assets,
  selected,
  limits,
  onChange,
  onDelete,
}: {
  title: string;
  hint: string;
  assets: ReferenceAssetOption[];
  selected: GenerationReferenceInput[];
  limits: Partial<Record<ReferenceMedia, number>>;
  onChange: (next: GenerationReferenceInput[]) => void;
  onDelete?: (asset: ReferenceAssetOption) => Promise<void>;
}) {
  const { t } = useI18n();
  const [pendingDelete, setPendingDelete] = useState<ReferenceAssetOption | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [preview, setPreview] = useState<{ kind: "image" | "video"; url: string; title: string } | null>(null);
  const selectedKeys = new Set(selected.map(keyOf));
  const visible = assets.filter((asset) => selectedKeys.has(keyOf(asset)) || (limits[asset.media] ?? 0) > 0);

  const toggle = (asset: ReferenceAssetOption) => {
    const key = keyOf(asset);
    if (selectedKeys.has(key)) {
      onChange(selected.filter((item) => keyOf(item) !== key));
      return;
    }
    const selectedCount = assets.filter(
      (item) => item.media === asset.media && selectedKeys.has(keyOf(item))
    ).length;
    if (selectedCount < (limits[asset.media] ?? 0)) {
      onChange([...selected, { kind: asset.kind, id: asset.id }]);
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete || !onDelete) return;
    setDeleting(true);
    try {
      await onDelete(pendingDelete);
      setPendingDelete(null);
    } catch {
      // The page owns the request error message; keep this dialog open so retry stays available.
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-border/60 bg-muted/20 p-3.5 shadow-2xs">
      <div>
        <p className="text-xs font-semibold text-foreground">{title}</p>
        <p className="mt-0.5 text-xs text-muted-foreground leading-relaxed">{hint}</p>
      </div>
      {visible.length === 0 ? (
        <p className="text-xs text-muted-foreground py-2">{t("episode.referenceEmpty")}</p>
      ) : (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
          {visible.map((asset) => {
            const active = selectedKeys.has(keyOf(asset));
            const selectedCount = assets.filter(
              (item) => item.media === asset.media && selectedKeys.has(keyOf(item))
            ).length;
            const disabled = !active && selectedCount >= (limits[asset.media] ?? 0);
            return (
              <div
                key={keyOf(asset)}
                className={cn(
                  "flex min-w-0 items-center rounded-lg border transition-all duration-150",
                  active
                    ? "border-primary/80 bg-primary/10 shadow-xs ring-1 ring-primary/30"
                    : "border-border/60 bg-background/60 hover:border-primary/50"
                )}
              >
                <button
                  type="button"
                  aria-pressed={active}
                  disabled={disabled}
                  onClick={() => toggle(asset)}
                  className={cn(
                    "flex min-w-0 flex-1 cursor-pointer items-center gap-2.5 p-2 text-left",
                    disabled && "cursor-not-allowed opacity-40"
                  )}
                >
                  <span
                    role="button"
                    tabIndex={0}
                    className="relative flex size-10 shrink-0 cursor-zoom-in items-center justify-center overflow-hidden rounded-md bg-muted group/thumb border border-border/40"
                    aria-label={t("episode.openPreview")}
                    onClick={(event) => {
                      event.stopPropagation();
                      if (asset.media === "image" || asset.media === "video") {
                        setPreview({ kind: asset.media, url: asset.url, title: asset.label });
                      }
                    }}
                    onKeyDown={(event) => {
                      if (event.key !== "Enter" && event.key !== " ") return;
                      event.preventDefault();
                      event.stopPropagation();
                      if (asset.media === "image" || asset.media === "video") {
                        setPreview({ kind: asset.media, url: asset.url, title: asset.label });
                      }
                    }}
                  >
                    {asset.media === "image" ? (
                      <Image src={asset.url} alt="" fill unoptimized sizes="40px" className="object-cover transition-transform duration-200 group-hover/thumb:scale-110" />
                    ) : asset.media === "video" ? (
                      <Film className="size-4 text-muted-foreground" />
                    ) : (
                      <Volume2 className="size-4 text-muted-foreground" />
                    )}
                    {active ? (
                      <span className="absolute inset-0 flex items-center justify-center bg-primary/80 text-primary-foreground backdrop-blur-2xs">
                        <Check className="size-4 stroke-[2.5]" />
                      </span>
                    ) : null}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-medium text-foreground">{asset.label}</span>
                    <span className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground">
                      {asset.media === "image" ? <ImageIcon className="size-3 text-muted-foreground/80" /> : null}
                      {t(`episode.referenceType.${asset.media}`)}
                    </span>
                  </span>
                </button>
                {onDelete ? (
                  <button
                    type="button"
                    title={t("episode.referenceDelete")}
                    aria-label={t("episode.referenceDeleteLabel", { name: asset.label })}
                    onClick={() => setPendingDelete(asset)}
                    className="mr-1.5 flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
      <p className="text-[11px] text-muted-foreground/80 font-mono">
        {(["image", "video", "audio"] as const)
          .filter((media) => (limits[media] ?? 0) > 0)
          .map((media) => {
            const count = assets.filter((asset) => asset.media === media && selectedKeys.has(keyOf(asset))).length;
            return t("episode.referenceLimit", {
              type: t(`episode.referenceType.${media}`),
              count,
              limit: limits[media] ?? 0,
            });
          })
          .join(" · ")}
      </p>

      <Dialog open={Boolean(pendingDelete)} onOpenChange={(open) => (open ? null : setPendingDelete(null))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("episode.referenceDelete")}</DialogTitle>
            <DialogDescription>
              {t("episode.referenceDeleteConfirm", { name: pendingDelete?.label ?? "" })}
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button variant="outline" disabled={deleting} onClick={() => setPendingDelete(null)} className="cursor-pointer">
              <X data-icon="inline-start" />
              {t("common.cancel")}
            </Button>
            <Button variant="destructive" disabled={deleting} onClick={() => void confirmDelete()} className="cursor-pointer">
              {deleting ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Trash2 data-icon="inline-start" />}
              {t("common.delete")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      <MediaPreviewDialog item={preview} onOpenChange={(open) => !open && setPreview(null)} />
    </div>
  );
}
