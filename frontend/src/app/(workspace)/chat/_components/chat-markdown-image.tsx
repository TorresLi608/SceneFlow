"use client";

import {
  Check,
  Copy,
  Download,
  ExternalLink,
  Eye,
  ImageIcon,
  ImageOff,
  Loader2,
  Maximize2,
  RefreshCw,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ComponentProps,
  type MouseEvent,
  type WheelEvent,
} from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { artifactBffUrl } from "@/lib/artifact-url";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface ChatMarkdownImageProps extends ComponentProps<"img"> {
  node?: unknown;
}

function extractDownloadFilename(url: string, alt?: string): string {
  if (alt && alt.trim()) {
    const cleanAlt = alt.trim().replace(/[\\/:*?"<>|]/g, "_");
    if (!cleanAlt.includes(".")) {
      return `${cleanAlt}.png`;
    }
    return cleanAlt;
  }
  try {
    const parsed = new URL(url);
    const parts = parsed.pathname.split("/");
    const last = parts.at(-1);
    if (last && last.includes(".")) {
      return decodeURIComponent(last);
    }
  } catch {
    // ignore
  }
  return "generated-image.png";
}

async function triggerDownload(url: string, filename: string) {
  // 必须走同源 BFF 代理地址，避免跨域或浏览器的 inline Content-Disposition 导致新标签页打开
  const targetUrl = artifactBffUrl(url);
  const res = await fetch(targetUrl);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  const blob = await res.blob();
  const blobUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
}

export function ChatMarkdownImage({
  node,
  src,
  alt,
  className,
  ...props
}: ChatMarkdownImageProps) {
  void node; // hast node injected by Streamdown
  const { t } = useI18n();
  const imgRef = useRef<HTMLImageElement>(null);

  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [isLoaded, setIsLoaded] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const [copied, setCopied] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  const url = typeof src === "string" ? src : "";
  const effectiveSrc = retryKey > 0 && url ? `${url}${url.includes("?") ? "&" : "?"}_retry=${retryKey}` : url;
  const filename = extractDownloadFilename(url, alt);

  // 当 URL 变更时派生重置
  const [prevSrc, setPrevSrc] = useState(effectiveSrc);
  if (prevSrc !== effectiveSrc) {
    setPrevSrc(effectiveSrc);
    setIsLoaded(false);
    setHasError(false);
  }

  // 缓存命中检测：如果图片早已在浏览器缓存中完成加载，立即标记为已完成
  useEffect(() => {
    const el = imgRef.current;
    if (el && el.complete && el.naturalWidth > 0) {
      setIsLoaded(true);
    }
  }, [effectiveSrc]);

  const handleOpenLightbox = useCallback(() => {
    setZoom(1);
    setLightboxOpen(true);
  }, []);

  const handleCopyLink = useCallback(
    (e?: MouseEvent) => {
      e?.stopPropagation();
      if (!url) return;
      void navigator.clipboard?.writeText(url).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      });
    },
    [url]
  );

  const handleDownload = useCallback(
    async (e?: MouseEvent) => {
      e?.stopPropagation();
      if (!url || isDownloading) return;
      setIsDownloading(true);
      try {
        await triggerDownload(url, filename);
      } catch {
        // 降级尝试在新标签页打开
        window.open(artifactBffUrl(url), "_blank");
      } finally {
        setIsDownloading(false);
      }
    },
    [url, filename, isDownloading]
  );

  const handleWheelZoom = useCallback((event: WheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (event.deltaY < 0) {
      setZoom((z) => Math.min(3, +(z + 0.25).toFixed(2)));
    } else {
      setZoom((z) => Math.max(0.5, +(z - 0.25).toFixed(2)));
    }
  }, []);

  const handleDoubleClick = useCallback(() => {
    setZoom((z) => (z > 1 ? 1 : 2));
  }, []);

  if (!url) {
    return null;
  }

  // 错误优雅容错卡片
  if (hasError) {
    return (
      <div
        role="alert"
        className="my-3 flex max-w-md flex-col gap-2.5 rounded-2xl border border-amber-500/30 bg-amber-500/5 p-3.5 text-xs text-amber-900 shadow-xs backdrop-blur-xs dark:border-amber-400/20 dark:bg-amber-400/5 dark:text-amber-200"
      >
        <div className="flex items-start gap-2.5">
          <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-amber-500/15 text-amber-600 dark:text-amber-400">
            <ImageOff className="size-4" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-foreground">{t("chat.imageLoadFailed")}</p>
            {alt ? <p className="mt-0.5 truncate text-[11px] opacity-75">{alt}</p> : null}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setHasError(false);
              setRetryKey((k) => k + 1);
            }}
            className="h-7 gap-1.5 rounded-lg border-amber-500/30 bg-background/80 px-2.5 text-xs text-foreground shadow-2xs hover:bg-amber-500/10"
          >
            <RefreshCw className="size-3" />
            <span>{t("chat.retryLoad")}</span>
          </Button>

          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-7 items-center gap-1.5 rounded-lg border border-border/60 bg-background/80 px-2.5 text-xs text-foreground transition-colors hover:bg-muted"
          >
            <ExternalLink className="size-3" />
            <span>{t("chat.openImage")}</span>
          </a>
        </div>
      </div>
    );
  }

  return (
    <>
      {/* 气泡卡片主体 */}
      <div
        className="group relative my-3 inline-block max-w-full overflow-hidden rounded-2xl border border-border/70 bg-card/60 shadow-xs transition-all duration-300 hover:border-primary/40 hover:shadow-md dark:border-border/60 dark:bg-card/40"
        data-streamdown="chat-image-card"
      >
        {/* 加载骨架屏 */}
        {!isLoaded ? (
          <div className="relative flex h-60 w-80 max-w-full items-center justify-center overflow-hidden rounded-2xl bg-muted/40 p-4">
            <Skeleton className="absolute inset-0 size-full" />
            <div className="relative z-10 flex flex-col items-center gap-2 text-muted-foreground/80">
              <div className="flex size-10 items-center justify-center rounded-xl bg-muted/70 shadow-xs">
                <ImageIcon className="size-5 text-muted-foreground animate-pulse" />
              </div>
              <span className="text-[11px] font-medium tracking-wide">
                {t("common.loading")}
              </span>
            </div>
          </div>
        ) : null}

        {/* 图片主体容器：始终保持在 DOM 中确保正常发起网络请求 */}
        <div
          onClick={handleOpenLightbox}
          className={cn(
            "relative cursor-zoom-in overflow-hidden",
            !isLoaded && "absolute inset-0 pointer-events-none opacity-0"
          )}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            ref={imgRef}
            {...props}
            src={effectiveSrc}
            alt={alt ?? ""}
            onLoad={() => setIsLoaded(true)}
            onError={() => {
              setIsLoaded(true);
              setHasError(true);
            }}
            className={cn(
              "max-h-[30rem] max-w-full object-contain transition-all duration-300 group-hover:scale-[1.015]",
              !isLoaded ? "opacity-0" : "opacity-100",
              className
            )}
          />

          {/* 悬停快捷操作栏（Hover Action Capsule） */}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-center p-3 opacity-0 transition-all duration-200 group-hover:opacity-100">
            <div className="pointer-events-auto flex items-center gap-1 rounded-full border border-border/80 bg-background/90 px-3 py-1.5 shadow-lg backdrop-blur-md dark:border-border/60 dark:bg-background/85">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleOpenLightbox();
                }}
                className="flex items-center gap-1.5 rounded-full px-2 py-1 text-xs font-semibold text-foreground transition-colors hover:bg-muted"
                title={t("chat.previewImage")}
              >
                <Eye className="size-3.5 text-primary" />
                <span>{t("chat.previewImage")}</span>
              </button>

              <div className="h-3 w-px bg-border" />

              <button
                type="button"
                onClick={handleDownload}
                disabled={isDownloading}
                className="rounded-full p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
                title={t("chat.downloadImage")}
              >
                {isDownloading ? (
                  <Loader2 className="size-3.5 animate-spin text-primary" />
                ) : (
                  <Download className="size-3.5" />
                )}
              </button>

              <button
                type="button"
                onClick={handleCopyLink}
                className="rounded-full p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                title={copied ? t("chat.linkCopied") : t("chat.copyLink")}
              >
                {copied ? (
                  <Check className="size-3.5 text-emerald-500" />
                ) : (
                  <Copy className="size-3.5" />
                )}
              </button>
            </div>
          </div>
        </div>

        {/* 底部标题 */}
        {alt && isLoaded ? (
          <div className="border-t border-border/50 bg-background/50 px-3.5 py-1.5 text-[11px] font-medium text-muted-foreground">
            {alt}
          </div>
        ) : null}
      </div>

      {/* 沉浸式全屏预览 Lightbox Dialog */}
      <Dialog
        open={lightboxOpen}
        onOpenChange={(open) => {
          setLightboxOpen(open);
          if (open) setZoom(1);
        }}
      >
        <DialogContent
          className="flex h-[92dvh] w-[95vw] max-w-6xl flex-col gap-0 overflow-hidden rounded-2xl border-border/40 bg-black/95 p-0 text-white shadow-2xl backdrop-blur-2xl"
          aria-describedby={undefined}
        >
          {/* 顶栏控制条 */}
          <DialogHeader className="flex h-14 shrink-0 flex-row items-center justify-between border-b border-white/10 px-4 py-0 sm:px-6">
            <div className="flex min-w-0 items-center gap-2.5">
              <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/20 text-primary">
                <Maximize2 className="size-4" />
              </div>
              <DialogTitle className="truncate text-sm font-semibold text-white">
                {alt || t("chat.previewImage")}
              </DialogTitle>
            </div>

            <div className="flex items-center gap-1.5 pr-8 sm:gap-2 sm:pr-10">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleCopyLink}
                className="h-8 gap-1.5 rounded-lg px-2.5 text-xs text-white/80 hover:bg-white/10 hover:text-white"
                title={t("chat.copyLink")}
              >
                {copied ? <Check className="size-3.5 text-emerald-400" /> : <Copy className="size-3.5" />}
                <span className="hidden sm:inline">{copied ? t("chat.linkCopied") : t("chat.copyLink")}</span>
              </Button>

              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleDownload}
                disabled={isDownloading}
                className="h-8 gap-1.5 rounded-lg px-2.5 text-xs text-white/80 hover:bg-white/10 hover:text-white disabled:opacity-50"
                title={t("chat.downloadImage")}
              >
                {isDownloading ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Download className="size-3.5" />
                )}
                <span className="hidden sm:inline">{t("chat.downloadImage")}</span>
              </Button>
            </div>
          </DialogHeader>

          {/* 中间图片画布：深色影院模式 */}
          <div
            onWheel={handleWheelZoom}
            onDoubleClick={handleDoubleClick}
            className="relative flex min-h-0 flex-1 select-none items-center justify-center overflow-hidden bg-black/80 p-2 sm:p-4"
          >
            {/* 网格微点点缀 */}
            <div className="pointer-events-none absolute inset-0 bg-grid-dots opacity-10" />

            <div
              className="relative flex size-full items-center justify-center transition-transform duration-200 ease-out"
              style={{ transform: `scale(${zoom})` }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={effectiveSrc}
                alt={alt ?? ""}
                className="max-h-[82dvh] max-w-full rounded-lg object-contain shadow-2xl"
              />
            </div>
          </div>

          {/* 底栏悬浮控制条（缩放操作） */}
          <div className="flex h-12 shrink-0 items-center justify-between border-t border-white/10 px-4 sm:px-6">
            <span className="text-xs text-white/50">
              {Math.round(zoom * 100)}%
            </span>

            <div className="flex items-center gap-1">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setZoom((z) => Math.max(0.5, +(z - 0.25).toFixed(2)))}
                disabled={zoom <= 0.5}
                className="size-8 p-0 text-white/80 hover:bg-white/10 hover:text-white"
                title={t("chat.zoomOut")}
              >
                <ZoomOut className="size-4" />
              </Button>

              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setZoom(1)}
                className="size-8 p-0 text-white/80 hover:bg-white/10 hover:text-white"
                title={t("chat.resetZoom")}
              >
                <RotateCcw className="size-3.5" />
              </Button>

              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setZoom((z) => Math.min(3, +(z + 0.25).toFixed(2)))}
                disabled={zoom >= 3}
                className="size-8 p-0 text-white/80 hover:bg-white/10 hover:text-white"
                title={t("chat.zoomIn")}
              >
                <ZoomIn className="size-4" />
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
