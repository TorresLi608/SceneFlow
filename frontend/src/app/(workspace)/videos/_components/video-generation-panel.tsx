"use client";

import { useMutation } from "@tanstack/react-query";
import { Download, Film, RotateCcw, Sparkles, Upload, X } from "lucide-react";
import Image from "next/image";
import { useEffect, useMemo, useRef, useState } from "react";

import { generateVideoAction } from "@/actions/video-generation-actions";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { configName } from "@/lib/config-format";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import type { UserConfig } from "@/types/auth";
import type { VideoFps, VideoReferenceInput, VideoResolution } from "@/types/video-generation";

const resolutionOptions: { value: VideoResolution; label: string; ratio: string }[] = [
  { value: "1280x720", label: "1280 × 720", ratio: "16:9" },
  { value: "720x1280", label: "720 × 1280", ratio: "9:16" },
  { value: "1024x1024", label: "1024 × 1024", ratio: "1:1" },
  { value: "1920x1080", label: "1920 × 1080", ratio: "16:9" },
];
const fpsOptions: VideoFps[] = [24, 30, 60];
const durationOptions = Array.from({ length: 12 }, (_, index) => index + 4);
const historyStorageKey = "sceneflow-video-generation-history-v1";

interface VideoHistoryItem {
  id: string;
  videoUrl: string;
  prompt: string;
  createdAt: string;
}

function configSelectValue(config: UserConfig) {
  return `${config.source}:${config.id}`;
}

function selectedConfigPayload(config: UserConfig | undefined) {
  if (!config) return {};
  return config.source === "official" ? { officialConfigId: config.id } : { configId: config.id };
}

function isVideoConfig(config: UserConfig) {
  return (
    config.purpose === "video" &&
    ["doubao", "gemini"].includes(config.provider) &&
    config.isEnabled &&
    config.isVerified &&
    Boolean(config.modelSeries.trim())
  );
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function readVideoHistory() {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(historyStorageKey) || "[]");
    return Array.isArray(parsed) ? (parsed as VideoHistoryItem[]) : [];
  } catch {
    return [];
  }
}

function saveVideoHistory(items: VideoHistoryItem[]) {
  window.localStorage.setItem(historyStorageKey, JSON.stringify(items.slice(0, 20)));
}

interface VideoGenerationPanelProps {
  configs: UserConfig[];
  officialConfigs: UserConfig[];
}

export function VideoGenerationPanel({ configs, officialConfigs }: VideoGenerationPanelProps) {
  const { t, formatDateTime } = useI18n();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedConfigId, setSelectedConfigId] = useState("");
  const [resolution, setResolution] = useState<VideoResolution>("1280x720");
  const [fps, setFps] = useState<VideoFps>(24);
  const [duration, setDuration] = useState(4);
  const [prompt, setPrompt] = useState("");
  const [reference, setReference] = useState<VideoReferenceInput | undefined>();
  const [videoUrl, setVideoUrl] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [isDownloading, setIsDownloading] = useState(false);
  const [history, setHistory] = useState<VideoHistoryItem[]>(readVideoHistory);

  const videoConfigs = useMemo(
    () => [...officialConfigs.filter(isVideoConfig), ...configs.filter(isVideoConfig)],
    [configs, officialConfigs]
  );
  const defaultConfigId = useMemo(() => {
    const config = videoConfigs.find((item) => item.isActive) ?? videoConfigs[0];
    return config ? configSelectValue(config) : "";
  }, [videoConfigs]);
  const effectiveConfigId = videoConfigs.some((config) => configSelectValue(config) === selectedConfigId)
    ? selectedConfigId
    : defaultConfigId;
  const selectedConfig = videoConfigs.find((config) => configSelectValue(config) === effectiveConfigId);
  const isGemini = selectedConfig?.provider === "gemini";

  const generateMutation = useMutation({
    mutationFn: generateVideoAction,
    onSuccess: (response, variables) => {
      const item = {
        id: `${Date.now()}`,
        videoUrl: response.video.url,
        prompt: variables.prompt,
        createdAt: new Date().toISOString(),
      };
      setVideoUrl(response.video.url);
      setHistory((current) => {
        const next = [item, ...current].slice(0, 20);
        saveVideoHistory(next);
        return next;
      });
      setErrorMessage(null);
    },
    onError: (error) => setErrorMessage(resolveRequestError(error, t("videos.generateFailed"))),
  });

  useEffect(() => {
    if (!generateMutation.isPending) return;
    const startedAt = Date.now();
    const timer = window.setInterval(() => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [generateMutation.isPending]);

  const selectModel = (value: string | null) => {
    const nextValue = value ?? "";
    setSelectedConfigId(nextValue);
    const nextConfig = videoConfigs.find((config) => configSelectValue(config) === nextValue);
    if (nextConfig?.provider === "gemini" && resolution === "1024x1024") {
      setResolution("1280x720");
    }
  };

  const addReference = async (file: File | undefined) => {
    if (!file) return;
    setErrorMessage(null);
    if (!file.type.match(/^image\/(png|jpeg|webp)$/) || file.size > 10 * 1024 * 1024) {
      setErrorMessage(t("videos.referenceLimit"));
      return;
    }
    setReference({ name: file.name, data: await readFileAsDataUrl(file) });
  };

  const generate = () => {
    const content = prompt.trim();
    if (!content || !selectedConfig || generateMutation.isPending) return;
    setElapsedSeconds(0);
    generateMutation.mutate({
      prompt: content,
      resolution,
      fps,
      duration,
      reference,
      ...selectedConfigPayload(selectedConfig),
    });
  };

  const downloadVideo = async () => {
    if (!videoUrl || isDownloading) return;
    setIsDownloading(true);
    setErrorMessage(null);
    try {
      const response = await fetch(videoUrl);
      if (!response.ok) throw new Error(`Download failed: ${response.status}`);
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = `sceneflow-video-${Date.now()}.mp4`;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    } catch {
      setErrorMessage(t("videos.downloadFailed"));
    } finally {
      setIsDownloading(false);
    }
  };

  const generatingLabel = t("videos.generatingWithSeconds", { seconds: elapsedSeconds });

  return (
    <div className="grid min-h-0 flex-1 bg-background md:grid-cols-[380px_minmax(0,1fr)]">
      <aside className="flex min-h-0 flex-col border-b border-border/60 bg-muted/20 p-4 md:border-r md:border-b-0">
        <div className="flex items-center gap-2">
          <Film className="size-4" />
          <h2 className="text-sm font-semibold">{t("home.videos")}</h2>
        </div>

        <div className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t("videos.model")}</label>
            <Select value={effectiveConfigId} onValueChange={selectModel}>
              <SelectTrigger>
                <SelectValue placeholder={t("videos.selectModel")}>
                  {selectedConfig ? configName(selectedConfig, t) : undefined}
                </SelectValue>
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                {videoConfigs.map((config) => (
                  <SelectItem key={configSelectValue(config)} value={configSelectValue(config)}>
                    {configName(config, t)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {videoConfigs.length === 0 ? <p className="text-xs text-amber-600">{t("videos.noModel")}</p> : null}
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t("videos.prompt")}</label>
            <Textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder={t("videos.promptPlaceholder")}
              className="min-h-28 resize-none"
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-3 md:grid-cols-1 lg:grid-cols-3">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">{t("videos.resolution")}</label>
              <Select value={resolution} onValueChange={(value) => setResolution(value as VideoResolution)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent alignItemWithTrigger={false}>
                  {resolutionOptions.map((item) => (
                    <SelectItem key={item.value} value={item.value} disabled={isGemini && item.ratio === "1:1"}>
                      {item.label} ({item.ratio})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium">{t("videos.fps")}</label>
              <Select value={String(fps)} onValueChange={(value) => setFps(Number(value) as VideoFps)}>
                <SelectTrigger><SelectValue>{fps} FPS</SelectValue></SelectTrigger>
                <SelectContent alignItemWithTrigger={false}>
                  {fpsOptions.map((item) => (
                    <SelectItem key={item} value={String(item)} disabled={item !== 24}>{item} FPS</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium">{t("videos.duration")}</label>
              <Select value={String(duration)} onValueChange={(value) => setDuration(Number(value))}>
                <SelectTrigger><SelectValue>{duration} s</SelectValue></SelectTrigger>
                <SelectContent alignItemWithTrigger={false} className="max-h-64">
                  {durationOptions.map((item) => <SelectItem key={item} value={String(item)}>{item} s</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <p className="text-xs leading-5 text-muted-foreground">{t("videos.capabilityHint")}</p>

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <label className="text-sm font-medium">{t("videos.reference")}</label>
              <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                {reference ? t("videos.imageToVideo") : t("videos.textToVideo")}
              </span>
            </div>
            <div className="flex gap-2">
              <Button type="button" variant="secondary" onClick={() => fileInputRef.current?.click()}>
                <Upload className="size-4" />
                {t("videos.uploadReference")}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setReference(undefined)} disabled={!reference}>
                {t("videos.clearReference")}
              </Button>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={(event) => {
                void addReference(event.target.files?.[0]);
                event.currentTarget.value = "";
              }}
            />
            <div className="relative flex aspect-video items-center justify-center overflow-hidden rounded-md border border-dashed border-muted-foreground/50 bg-background/40 text-xs text-muted-foreground">
              {reference ? (
                <>
                  <Image src={reference.data} alt="" fill unoptimized sizes="348px" className="object-contain" />
                  <button
                    type="button"
                    onClick={() => setReference(undefined)}
                    className="absolute top-2 right-2 inline-flex size-7 items-center justify-center rounded-md bg-background/85 text-foreground"
                    aria-label={t("videos.removeReference")}
                  >
                    <X className="size-4" />
                  </button>
                </>
              ) : t("videos.referenceEmpty")}
            </div>
            <p className="text-xs leading-5 text-muted-foreground">{t("videos.referenceHint")}</p>
          </div>
        </div>

        <div className="mt-4 border-t border-border/70 pt-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">{t("videos.history")}</h3>
            <span className="text-xs text-muted-foreground">{history.length}</span>
          </div>
          {history.length ? (
            <div className="max-h-44 space-y-2 overflow-y-auto pr-1">
              {history.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setVideoUrl(item.videoUrl)}
                  className="flex w-full gap-2 rounded-md border border-border/70 bg-background/60 p-2 text-left transition-colors hover:bg-muted/60"
                  aria-label={t("videos.viewHistoryItem")}
                >
                  <span className="flex size-14 shrink-0 items-center justify-center rounded-md bg-muted"><Film className="size-5" /></span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-medium">{item.prompt}</span>
                    <span className="mt-1 block text-xs text-muted-foreground">{formatDateTime(item.createdAt)}</span>
                  </span>
                </button>
              ))}
            </div>
          ) : <p className="text-xs text-muted-foreground">{t("videos.historyEmpty")}</p>}
        </div>

        <div className="mt-4 border-t border-border/70 pt-4">
          <Button className="w-full" onClick={generate} disabled={!prompt.trim() || !selectedConfig || generateMutation.isPending}>
            <Sparkles className="size-4" />
            {generateMutation.isPending ? generatingLabel : t("videos.generateNow")}
          </Button>
        </div>
      </aside>

      <section className="flex min-h-0 min-w-0 flex-col p-4 md:p-6">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">{t("videos.preview")}</h2>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={generate} disabled={!videoUrl || generateMutation.isPending}>
              <RotateCcw className="size-4" />
              {t("videos.regenerate")}
            </Button>
            <Button variant="secondary" size="sm" onClick={downloadVideo} disabled={!videoUrl || isDownloading}>
              <Download className="size-4" />
              {t("videos.download")}
            </Button>
          </div>
        </div>

        <div className="mt-4 flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-md border border-dashed border-muted-foreground/50 bg-muted/10">
          {generateMutation.isPending ? (
            <div className="text-center text-sm text-muted-foreground">
              <Sparkles className="mx-auto mb-3 size-5 animate-pulse" />
              {generatingLabel}
            </div>
          ) : videoUrl ? (
            <video key={videoUrl} src={videoUrl} controls playsInline className="max-h-full max-w-full" />
          ) : (
            <div className="text-center text-sm text-muted-foreground">
              <Film className="mx-auto mb-3 size-5" />
              {t("videos.emptyPreview")}
            </div>
          )}
        </div>
        {errorMessage ? <p className="mt-3 text-sm text-amber-600">{errorMessage}</p> : null}
      </section>
    </div>
  );
}
