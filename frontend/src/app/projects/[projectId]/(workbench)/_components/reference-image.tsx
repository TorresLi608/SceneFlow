"use client";

import { ImagePlus, Loader2, Sparkles, Square, Upload } from "lucide-react";
import Image from "next/image";
import { useRef } from "react";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { IMAGE_TYPES, readImageFile } from "@/lib/image-file";
import { cn } from "@/lib/utils";

export interface ReferenceImageProps {
  url: string | null;
  /** Label on the draw button; characters say "turnaround sheet", props say "prop image". */
  generateLabel: string;
  generatingLabel: string;
  uploadLabel: string;
  busy?: boolean;
  generating?: boolean;
  /** Blocks starting a draw without blocking the stop button that replaces it. */
  generateDisabled?: boolean;
  generateTitle?: string;
  className?: string;
  onGenerate: () => void;
  /** Supplied turns the draw button into a stop button while a draw is in flight. */
  onStop?: () => void;
  onUpload: (dataUrl: string) => void;
  onError: (message: string) => void;
}

/**
 * One reference image with the two ways to get it: draw it, or upload your own. Shared
 * because a character state and a prop differ only in wording here.
 */
export function ReferenceImage({
  url,
  generateLabel,
  generatingLabel,
  uploadLabel,
  busy = false,
  generating = false,
  generateDisabled = false,
  generateTitle,
  className,
  onGenerate,
  onStop,
  onUpload,
  onError,
}: ReferenceImageProps) {
  const { t } = useI18n();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const pick = async (file: File | undefined) => {
    if (!file) return;
    const result = await readImageFile(file);
    if (!result.ok) {
      onError(
        result.reason === "unsupported"
          ? t("reference.imageUnsupported")
          : result.reason === "too-large"
            ? t("reference.imageTooLarge")
            : t("reference.uploadFailed")
      );
      return;
    }
    onUpload(result.dataUrl);
  };

  // Only offer to stop when the caller can actually stop it; otherwise the button keeps
  // its old spinner-and-disabled behaviour rather than pretending to be interruptible.
  const stoppable = generating && Boolean(onStop);

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <span className="relative flex aspect-[3/2] w-full items-center justify-center overflow-hidden rounded-lg border border-border/60 bg-muted">
        {url ? (
          <Image src={url} alt="" fill unoptimized sizes="(min-width: 768px) 33vw, 100vw" className="object-contain" />
        ) : (
          <span className="flex flex-col items-center gap-1 text-xs text-muted-foreground">
            <ImagePlus className="size-6" />
            {t("reference.noImage")}
          </span>
        )}
      </span>
      <div className="flex flex-wrap gap-2">
        <input
          ref={fileInputRef}
          type="file"
          accept={IMAGE_TYPES.join(",")}
          className="hidden"
          onChange={(event) => {
            void pick(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
        <Button
          type="button"
          variant={stoppable ? "destructive" : "outline"}
          size="sm"
          disabled={stoppable ? false : busy || generateDisabled}
          title={generateTitle}
          onClick={stoppable ? onStop : onGenerate}
          className={cn(stoppable && "animate-pulse font-medium")}
        >
          {stoppable ? (
            <Square data-icon="inline-start" className="size-3 fill-current" />
          ) : generating ? (
            <Loader2 data-icon="inline-start" className="animate-spin" />
          ) : (
            <Sparkles data-icon="inline-start" />
          )}
          {stoppable ? t("common.stopGeneration") : generating ? generatingLabel : generateLabel}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => fileInputRef.current?.click()}
        >
          <Upload data-icon="inline-start" />
          {uploadLabel}
        </Button>
      </div>
    </div>
  );
}
