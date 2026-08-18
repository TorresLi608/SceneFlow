"use client";

import { useMutation } from "@tanstack/react-query";
import { Download, Film, ImageIcon, Link2, Loader2, Music2, RotateCcw, Sparkles, Upload, Video, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { generateVideoAction } from "@/actions/video-generation-actions";
import { optimizePromptAction } from "@/actions/prompt-actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { artifactBffUrl } from "@/lib/artifact-url";
import { configName } from "@/lib/config-format";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import type { UserConfig } from "@/types/auth";
import type { VideoAspectRatio, VideoFps, VideoQuality, VideoReferenceInput } from "@/types/video-generation";
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
    ["doubao", "gemini", "qwen"].includes(config.provider) &&
    config.isEnabled &&
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
  const videoInputRef = useRef<HTMLInputElement>(null);
  const audioInputRef = useRef<HTMLInputElement>(null);
  const [selectedConfigId, setSelectedConfigId] = useState("");
  const [aspectRatio, setAspectRatio] = useState<VideoAspectRatio>("16:9");
  const [fps, setFps] = useState<VideoFps>(24);
  const [quality, setQuality] = useState<VideoQuality>("720p");
  const [duration, setDuration] = useState(3);
  const [promptExtend, setPromptExtend] = useState(false);
  const [promptLanguage, setPromptLanguage] = useState<"auto" | "zh" | "en">("auto");
  const [prompt, setPrompt] = useState("");
  const [references, setReferences] = useState<VideoReferenceInput[]>([]);
  const [referenceVideos, setReferenceVideos] = useState<VideoReferenceInput[]>([]);
  const [referenceAudios, setReferenceAudios] = useState<VideoReferenceInput[]>([]);
  const [referenceImageUrl, setReferenceImageUrl] = useState("");
  const [referenceVideoUrl, setReferenceVideoUrl] = useState("");
  const [referenceAudioUrl, setReferenceAudioUrl] = useState("");
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
  const capabilities = selectedConfig?.videoCapabilities;
  const selectedQuality = capabilities?.qualities.includes(quality) ? quality : capabilities?.qualities[0] ?? "720p";
  const selectedAspectRatio = capabilities?.aspectRatios.includes(aspectRatio) ? aspectRatio : capabilities?.aspectRatios[0] ?? "16:9";
  const selectedFps = capabilities?.fps.includes(fps) ? fps : capabilities?.fps[0] ?? 24;
  const selectedDuration = capabilities ? Math.min(capabilities.maxDuration, Math.max(capabilities.minDuration, duration)) : duration;
  const selectedPromptExtend = Boolean(capabilities?.promptExtend && promptExtend);
  const resolvedVideoUrl = artifactBffUrl(videoUrl);
  const durationOptions = capabilities
    ? Array.from({ length: capabilities.maxDuration - capabilities.minDuration + 1 }, (_, index) => capabilities.minDuration + index)
    : [];

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

  const optimizeMutation = useMutation({
    mutationFn: () => optimizePromptAction({
      kind: "video",
      prompt: prompt.trim(),
      context: {
        outputLanguage: promptLanguage,
        aspectRatio: selectedAspectRatio,
        quality: selectedQuality,
        duration: selectedDuration,
        fps: selectedFps,
      },
    }),
    onSuccess: (response) => {
      setPrompt(response.prompt);
      setErrorMessage(null);
    },
    onError: (error) => setErrorMessage(resolveRequestError(error, t("common.optimizePromptFailed"))),
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
    const nextCapabilities = nextConfig?.videoCapabilities;
    setReferences((current) => nextCapabilities?.maxReferenceImages ? current.slice(0, nextCapabilities.maxReferenceImages) : []);
    setReferenceVideos((current) => nextCapabilities?.maxReferenceVideos ? current.slice(0, nextCapabilities.maxReferenceVideos) : []);
    setReferenceAudios((current) => nextCapabilities?.maxReferenceAudios ? current.slice(0, nextCapabilities.maxReferenceAudios) : []);
    setQuality(nextCapabilities?.qualities[0] ?? "720p");
    setAspectRatio(nextCapabilities?.aspectRatios[0] ?? "16:9");
    setFps(nextCapabilities?.fps[0] ?? 24);
    setDuration(nextCapabilities?.minDuration ?? 3);
    setPromptExtend(false);
  };

  const addReferences = async (files: FileList | null) => {
    if (!files || !capabilities) return;
    const selected = Array.from(files).slice(0, Math.max(0, capabilities.maxReferenceImages - references.length));
    if (selected.some((file) => !file.type.match(/^image\/(png|jpeg|webp)$/) || file.size > 10 * 1024 * 1024)) {
      setErrorMessage(t("videos.referenceLimit"));
      return;
    }
    const loaded = await Promise.all(selected.map(async (file) => ({ name: file.name, data: await readFileAsDataUrl(file) })));
    setReferences((current) => [...current, ...loaded].slice(0, capabilities.maxReferenceImages));
  };

  const addMedia = async (file: File | undefined, kind: "video" | "audio") => {
    if (!file) return;
    setErrorMessage(null);
    const allowed = kind === "video" ? /^video\/(mp4|quicktime|webm)$/ : /^audio\/(mpeg|wav|x-wav|mp4)$/;
    if (!allowed.test(file.type) || file.size > 50 * 1024 * 1024) {
      setErrorMessage(t(kind === "video" ? "videos.referenceVideoLimit" : "videos.referenceAudioLimit"));
      return;
    }
    const value = { name: file.name, data: await readFileAsDataUrl(file) };
    if (kind === "video") setReferenceVideos((current) => [...current, value].slice(0, capabilities?.maxReferenceVideos ?? 0));
    else setReferenceAudios((current) => [...current, value].slice(0, capabilities?.maxReferenceAudios ?? 0));
  };

  const addUrl = (kind: "image" | "video" | "audio") => {
    const current = kind === "image" ? referenceImageUrl : kind === "video" ? referenceVideoUrl : referenceAudioUrl;
    const url = current.trim();
    if (!url) return;
    try {
      const parsed = new URL(url);
      if (!(parsed.protocol === "http:" || parsed.protocol === "https:")) throw new Error();
    } catch {
      setErrorMessage(t("videos.invalidReferenceUrl"));
      return;
    }
    if (kind === "image") {
      setReferences((items) => [...items, { url }].slice(0, capabilities?.maxReferenceImages ?? 0));
      setReferenceImageUrl("");
    } else if (kind === "video") {
      setReferenceVideos((items) => [...items, { url }].slice(0, capabilities?.maxReferenceVideos ?? 0));
      setReferenceVideoUrl("");
    } else {
      setReferenceAudios((items) => [...items, { url }].slice(0, capabilities?.maxReferenceAudios ?? 0));
      setReferenceAudioUrl("");
    }
    setErrorMessage(null);
  };

  const generate = () => {
    const content = prompt.trim();
    if (!content || !selectedConfig || generateMutation.isPending) return;
    setElapsedSeconds(0);
    generateMutation.mutate({
      prompt: content,
      duration: selectedDuration,
      references,
      ...(referenceVideos.length ? { referenceVideos } : {}),
      ...(referenceAudios.length ? { referenceAudios } : {}),
      ...(capabilities?.qualities.length ? { quality: selectedQuality } : {}),
      ...(capabilities?.aspectRatios.length ? { aspectRatio: selectedAspectRatio } : {}),
      ...(capabilities?.fps.length ? { fps: selectedFps } : {}),
      ...(capabilities?.promptExtend ? { promptExtend: selectedPromptExtend } : {}),
      ...selectedConfigPayload(selectedConfig),
    });
  };

  const downloadVideo = async () => {
    if (!videoUrl || isDownloading) return;
    setIsDownloading(true);
    setErrorMessage(null);
    try {
      const response = await fetch(resolvedVideoUrl);
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
            <div className="flex items-center justify-between gap-2">
              <label className="text-sm font-medium">{t("videos.prompt")}</label>
              <div className="flex items-center gap-1">
                <Select value={promptLanguage} onValueChange={(value) => setPromptLanguage((value ?? "auto") as "auto" | "zh" | "en")}>
                  <SelectTrigger className="h-8 w-24" aria-label={t("common.promptLanguage")}><SelectValue /></SelectTrigger>
                  <SelectContent alignItemWithTrigger={false}>
                    <SelectItem value="auto">{t("common.promptLanguageAuto")}</SelectItem>
                    <SelectItem value="zh">{t("common.promptLanguageZh")}</SelectItem>
                    <SelectItem value="en">{t("common.promptLanguageEn")}</SelectItem>
                  </SelectContent>
                </Select>
                <Button type="button" variant="ghost" size="sm" disabled={!prompt.trim() || optimizeMutation.isPending} onClick={() => optimizeMutation.mutate()}>
                  {optimizeMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                  {optimizeMutation.isPending ? t("common.optimizingPrompt") : t("common.optimizePrompt")}
                </Button>
              </div>
            </div>
            <Textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder={t("videos.promptPlaceholder")}
              className="min-h-28 resize-none"
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-1 lg:grid-cols-2">
            {capabilities?.qualities.length ? (
              <div className="space-y-1.5">
                <label className="text-sm font-medium">{t("videos.quality")}</label>
                <Select value={selectedQuality} onValueChange={(value) => setQuality(value as VideoQuality)}>
                  <SelectTrigger><SelectValue>{selectedQuality}</SelectValue></SelectTrigger>
                  <SelectContent alignItemWithTrigger={false}>
                    {capabilities.qualities.map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            ) : null}

            {capabilities?.aspectRatios.length ? (
              <div className="space-y-1.5">
                <label className="text-sm font-medium">{t("videos.aspectRatio")}</label>
                <Select value={selectedAspectRatio} onValueChange={(value) => setAspectRatio(value as VideoAspectRatio)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent alignItemWithTrigger={false}>
                    {capabilities.aspectRatios.map((item) => <SelectItem key={item} value={item}>{item === "adaptive" ? t("videos.aspectRatioAdaptive") : item}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            ) : null}

            {capabilities?.fps.length ? (
              <div className="space-y-1.5">
                <label className="text-sm font-medium">{t("videos.fps")}</label>
                <Select value={String(selectedFps)} onValueChange={(value) => setFps(Number(value) as VideoFps)}>
                  <SelectTrigger><SelectValue>{selectedFps} FPS</SelectValue></SelectTrigger>
                  <SelectContent alignItemWithTrigger={false}>
                    {capabilities.fps.map((item) => <SelectItem key={item} value={String(item)}>{item} FPS</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            ) : null}

            <div className="space-y-1.5">
              <label className="text-sm font-medium">{t("videos.duration")}</label>
              <Select value={String(selectedDuration)} onValueChange={(value) => setDuration(Number(value))}>
                <SelectTrigger><SelectValue>{selectedDuration} s</SelectValue></SelectTrigger>
                <SelectContent alignItemWithTrigger={false} className="max-h-64">
                  {durationOptions.map((item) => <SelectItem key={item} value={String(item)}>{item} s</SelectItem>)}
                </SelectContent>
              </Select>
            </div>

            {capabilities?.promptExtend ? (
              <label className="flex min-h-8 items-center justify-between gap-3 text-sm">
                <span className="font-medium">{t("videos.promptExtend")}</span>
                <Switch checked={selectedPromptExtend} onCheckedChange={setPromptExtend} />
              </label>
            ) : null}
          </div>

          {capabilities && (capabilities.referenceImages || capabilities.referenceVideo || capabilities.referenceAudio) ? <div className="space-y-4 border-t border-border/70 pt-4">
            <div className="flex items-center justify-between gap-2">
              <label className="text-sm font-medium">{t("videos.inputMedia")}</label>
              <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                {referenceVideos.length ? t("videos.videoToVideo") : references.length ? t("videos.imageToVideo") : t("videos.textToVideo")}
              </span>
            </div>
            {capabilities.referenceImages ? <MediaReferenceSection
              kind="image"
              label={t("videos.referenceImagesLabel")}
              values={references}
              max={capabilities.maxReferenceImages}
              required={capabilities.referenceImagesRequired}
              draftUrl={referenceImageUrl}
              setDraftUrl={setReferenceImageUrl}
              onAddUrl={() => addUrl("image")}
              onUpload={() => fileInputRef.current?.click()}
              onClear={() => setReferences([])}
              onRemove={(index) => setReferences((current) => current.filter((_, item) => item !== index))}
              uploadEnabled={selectedConfig?.provider === "qwen"}
              uploadLabel={t("videos.uploadReferenceImage")}
              requiredLabel={t("videos.referenceRequired")}
              urlPlaceholder={t("videos.referenceUrlPlaceholder")}
              addUrlLabel={t("videos.addReferenceUrl")}
              clearLabel={t("videos.clearReferences")}
              removeLabel={t("videos.removeReference")}
            /> : null}
            {capabilities.referenceImages ? <>
              <input ref={fileInputRef} type="file" multiple accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(event) => { void addReferences(event.target.files); event.currentTarget.value = ""; }} />
            </> : null}
            {capabilities.referenceVideo ? <MediaReferenceSection
              kind="video"
              label={t("videos.referenceVideo")}
              values={referenceVideos}
              max={capabilities.maxReferenceVideos}
              required={capabilities.referenceVideosRequired}
              draftUrl={referenceVideoUrl}
              setDraftUrl={setReferenceVideoUrl}
              onAddUrl={() => addUrl("video")}
              onUpload={() => videoInputRef.current?.click()}
              onClear={() => setReferenceVideos([])}
              onRemove={(index) => setReferenceVideos((current) => current.filter((_, item) => item !== index))}
              uploadEnabled={selectedConfig?.provider === "qwen"}
              uploadLabel={t("videos.uploadReferenceVideo")}
              requiredLabel={t("videos.referenceVideoRequired")}
              urlPlaceholder={t("videos.referenceUrlPlaceholder")}
              addUrlLabel={t("videos.addReferenceUrl")}
              clearLabel={t("videos.clearReferenceVideos")}
              removeLabel={t("videos.removeReference")}
            /> : null}
            {capabilities.referenceAudio ? <MediaReferenceSection
              kind="audio"
              label={t("videos.referenceAudio")}
              values={referenceAudios}
              max={capabilities.maxReferenceAudios}
              required={capabilities.referenceAudiosRequired}
              draftUrl={referenceAudioUrl}
              setDraftUrl={setReferenceAudioUrl}
              onAddUrl={() => addUrl("audio")}
              onUpload={() => audioInputRef.current?.click()}
              onClear={() => setReferenceAudios([])}
              onRemove={(index) => setReferenceAudios((current) => current.filter((_, item) => item !== index))}
              uploadEnabled={selectedConfig?.provider === "qwen"}
              uploadLabel={t("videos.uploadReferenceAudio")}
              requiredLabel={t("videos.referenceAudioRequired")}
              urlPlaceholder={t("videos.referenceUrlPlaceholder")}
              addUrlLabel={t("videos.addReferenceUrl")}
              clearLabel={t("videos.clearReferenceAudios")}
              removeLabel={t("videos.removeReference")}
            /> : null}
            <input ref={videoInputRef} type="file" accept="video/mp4,video/quicktime,video/webm" className="hidden" onChange={(event) => { void addMedia(event.target.files?.[0], "video"); event.currentTarget.value = ""; }} />
            <input ref={audioInputRef} type="file" accept="audio/mpeg,audio/wav,audio/mp4" className="hidden" onChange={(event) => { void addMedia(event.target.files?.[0], "audio"); event.currentTarget.value = ""; }} />
          </div> : null}
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
          <Button className="w-full" onClick={generate} disabled={!prompt.trim() || !selectedConfig || generateMutation.isPending || Boolean(capabilities?.referenceImagesRequired && references.length === 0) || Boolean(capabilities?.referenceVideosRequired && referenceVideos.length === 0) || Boolean(capabilities?.referenceAudiosRequired && referenceAudios.length === 0)}>
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
            <video key={resolvedVideoUrl} src={resolvedVideoUrl} controls playsInline className="max-h-full max-w-full" />
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

function MediaReferenceSection({ kind, label, values, max, required, draftUrl, setDraftUrl, onAddUrl, onUpload, onClear, onRemove, uploadEnabled, uploadLabel, requiredLabel, urlPlaceholder, addUrlLabel, clearLabel, removeLabel }: {
  kind: "image" | "video" | "audio";
  label: string;
  values: VideoReferenceInput[];
  max: number;
  required: boolean;
  draftUrl: string;
  setDraftUrl: (value: string) => void;
  onAddUrl: () => void;
  onUpload: () => void;
  onClear: () => void;
  onRemove: (index: number) => void;
  uploadEnabled: boolean;
  uploadLabel: string;
  requiredLabel: string;
  urlPlaceholder: string;
  addUrlLabel: string;
  clearLabel: string;
  removeLabel: string;
}) {
  const Icon = kind === "image" ? ImageIcon : kind === "video" ? Video : Music2;
  return <div className="space-y-2 rounded-md border border-border/70 p-3">
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-center gap-2 text-xs font-medium"><Icon className="size-4" />{label}</span>
      <span className="text-xs text-muted-foreground">{values.length}/{max}</span>
    </div>
    <div className="flex gap-2">
      {uploadEnabled ? <Button type="button" size="sm" variant="secondary" disabled={values.length >= max} onClick={onUpload}><Upload className="size-4" />{uploadLabel}</Button> : null}
      {values.length ? <Button type="button" size="sm" variant="ghost" onClick={onClear}>{clearLabel}</Button> : null}
    </div>
    <div className="flex gap-2">
      <Input value={draftUrl} onChange={(event) => setDraftUrl(event.target.value)} placeholder={urlPlaceholder} disabled={values.length >= max} />
      <Button type="button" size="sm" variant="outline" disabled={!draftUrl.trim() || values.length >= max} onClick={onAddUrl}><Link2 className="size-4" />{addUrlLabel}</Button>
    </div>
    {values.length ? <div className="space-y-1.5">{values.map((value, index) => <div key={`${value.url || value.name || "media"}-${index}`} className="flex items-center gap-2 rounded bg-muted/40 px-2 py-1.5 text-xs"><span className="min-w-0 flex-1 truncate">{value.name || value.url}</span><Button type="button" size="icon-xs" variant="ghost" onClick={() => onRemove(index)} aria-label={removeLabel} title={removeLabel}><X className="size-3.5" /></Button></div>)}</div> : null}
    {required && values.length === 0 ? <p className="text-xs text-amber-600">{requiredLabel}</p> : null}
  </div>;
}
