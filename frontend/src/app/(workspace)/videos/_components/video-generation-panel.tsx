"use client";

import { useMutation } from "@tanstack/react-query";
import {
  AudioLines,
  Download,
  Film,
  History,
  ImageIcon,
  Loader2,
  Plus,
  RotateCcw,
  Sparkles,
  Trash2,
  Upload,
  Video,
} from "lucide-react";
import Image from "next/image";
import { useEffect, useMemo, useRef, useState } from "react";

import { generateVideoAction } from "@/actions/video-generation-actions";
import { optimizePromptAction } from "@/actions/prompt-actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { artifactBffUrl } from "@/lib/artifact-url";
import { configName } from "@/lib/config-format";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import type { UserConfig } from "@/types/auth";
import type {
  VideoAspectRatio,
  VideoFps,
  VideoQuality,
  VideoReferenceInput,
} from "@/types/video-generation";

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
  return config.source === "official"
    ? { officialConfigId: config.id }
    : { configId: config.id };
}

function isVideoConfig(config: UserConfig) {
  return (
    config.purpose === "video" &&
    ["doubao", "qwen"].includes(config.provider) &&
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

export function VideoGenerationPanel({
  configs,
  officialConfigs,
}: VideoGenerationPanelProps) {
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
  const effectiveConfigId = videoConfigs.some(
    (config) => configSelectValue(config) === selectedConfigId
  )
    ? selectedConfigId
    : defaultConfigId;
  const selectedConfig = videoConfigs.find(
    (config) => configSelectValue(config) === effectiveConfigId
  );
  const capabilities = selectedConfig?.videoCapabilities;
  const usesQwenTemporaryUpload = selectedConfig?.provider === "qwen";
  const visibleReferences = usesQwenTemporaryUpload ? references : references.filter((item) => item.url);
  const visibleReferenceVideos = usesQwenTemporaryUpload
    ? referenceVideos
    : referenceVideos.filter((item) => item.url);
  const visibleReferenceAudios = usesQwenTemporaryUpload
    ? referenceAudios
    : referenceAudios.filter((item) => item.url);
  const selectedQuality = capabilities?.qualities.includes(quality)
    ? quality
    : capabilities?.qualities[0] ?? "720p";
  const selectedAspectRatio = capabilities?.aspectRatios.includes(aspectRatio)
    ? aspectRatio
    : capabilities?.aspectRatios[0] ?? "16:9";
  const selectedFps = capabilities?.fps.includes(fps)
    ? fps
    : capabilities?.fps[0] ?? 24;
  const selectedDuration = capabilities
    ? Math.min(capabilities.maxDuration, Math.max(capabilities.minDuration, duration))
    : duration;
  const selectedPromptExtend = Boolean(capabilities?.promptExtend && promptExtend);
  const resolvedVideoUrl = artifactBffUrl(videoUrl);
  const durationOptions = capabilities
    ? Array.from(
        { length: capabilities.maxDuration - capabilities.minDuration + 1 },
        (_, index) => capabilities.minDuration + index
      )
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
    onError: (error) =>
      setErrorMessage(resolveRequestError(error, t("videos.generateFailed"))),
  });

  const optimizeMutation = useMutation({
    mutationFn: () =>
      optimizePromptAction({
        kind: "video",
        prompt: prompt.trim(),
        context: {
          outputLanguage: promptLanguage,
          aspectRatio: selectedAspectRatio,
          quality: selectedQuality,
          duration: selectedDuration,
        },
      }),
    onSuccess: (response) => {
      setPrompt(response.prompt);
      setErrorMessage(null);
    },
    onError: (error) =>
      setErrorMessage(resolveRequestError(error, t("common.optimizePromptFailed"))),
  });

  useEffect(() => {
    if (!generateMutation.isPending) return;
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [generateMutation.isPending]);

  const addReferences = async (
    files: FileList | null,
    target: "images" | "videos" | "audios"
  ) => {
    if (!files) return;
    setErrorMessage(null);
    if (target === "images") {
      const limit = capabilities?.maxReferenceImages ?? 1;
      const next = [...references];
      for (const file of Array.from(files).slice(0, Math.max(0, limit - next.length))) {
        if (!file.type.startsWith("image/") || file.size > 10 * 1024 * 1024) {
          setErrorMessage(t("videos.referenceLimit"));
          continue;
        }
        next.push({ name: file.name, data: await readFileAsDataUrl(file) });
      }
      setReferences(next);
    } else if (target === "videos") {
      const limit = capabilities?.maxReferenceVideos ?? 1;
      const next = [...referenceVideos];
      for (const file of Array.from(files).slice(0, Math.max(0, limit - next.length))) {
        if (!file.type.startsWith("video/") || file.size > 50 * 1024 * 1024) {
          setErrorMessage(t("videos.referenceVideoLimit"));
          continue;
        }
        next.push({ name: file.name, data: await readFileAsDataUrl(file) });
      }
      setReferenceVideos(next);
    } else {
      const limit = capabilities?.maxReferenceAudios ?? 1;
      const next = [...referenceAudios];
      for (const file of Array.from(files).slice(0, Math.max(0, limit - next.length))) {
        if (!file.type.startsWith("audio/") || file.size > 50 * 1024 * 1024) {
          setErrorMessage(t("videos.referenceAudioLimit"));
          continue;
        }
        next.push({ name: file.name, data: await readFileAsDataUrl(file) });
      }
      setReferenceAudios(next);
    }
  };

  const addReferenceUrl = (target: "images" | "videos" | "audios") => {
    const value = (
      target === "images"
        ? referenceImageUrl
        : target === "videos"
          ? referenceVideoUrl
          : referenceAudioUrl
    ).trim();
    if (!value) return;
    try {
      const url = new URL(value);
      if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error();
    } catch {
      setErrorMessage(t("videos.invalidReferenceUrl"));
      return;
    }

    const items =
      target === "images"
        ? visibleReferences
        : target === "videos"
          ? visibleReferenceVideos
          : visibleReferenceAudios;
    const maximum =
      target === "images"
        ? capabilities?.maxReferenceImages
        : target === "videos"
          ? capabilities?.maxReferenceVideos
          : capabilities?.maxReferenceAudios;
    if (!maximum || items.length >= maximum) return;

    if (target === "images") {
      setReferences((current) => [...current, { url: value }]);
      setReferenceImageUrl("");
    } else if (target === "videos") {
      setReferenceVideos((current) => [...current, { url: value }]);
      setReferenceVideoUrl("");
    } else {
      setReferenceAudios((current) => [...current, { url: value }]);
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
      aspectRatio: selectedAspectRatio,
      fps: selectedFps,
      quality: selectedQuality,
      duration: selectedDuration,
      promptExtend: selectedPromptExtend,
      references: visibleReferences,
      referenceVideos: visibleReferenceVideos,
      referenceAudios: visibleReferenceAudios,
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

  const generatingLabel = t("videos.generatingVideoWithSeconds", {
    seconds: elapsedSeconds,
  });

  return (
    <div className="grid min-h-0 flex-1 bg-background lg:grid-cols-[380px_minmax(0,1fr)]">
      {/* 控制侧边栏 */}
      <aside className="flex min-h-0 flex-col border-b border-border/70 bg-card/40 p-4 backdrop-blur-xl lg:border-r lg:border-b-0 lg:p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Video className="size-4" />
            </div>
            <h2 className="text-sm font-bold tracking-tight text-foreground">
              {t("home.videos")}
            </h2>
          </div>
          <Badge variant="secondary" className="text-[10px]">
            AI Studio
          </Badge>
        </div>

        <div className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto px-1 chat-message-list-scrollbar">
          {/* 模型选择 */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-foreground/90">
              {t("videos.model")}
            </label>
            <Select
              value={effectiveConfigId}
              onValueChange={(val) => setSelectedConfigId(val ?? "")}
            >
              <SelectTrigger className="h-9 text-xs">
                <SelectValue placeholder={t("videos.selectModel")}>
                  {selectedConfig ? configName(selectedConfig, t) : undefined}
                </SelectValue>
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                {videoConfigs.map((config) => (
                  <SelectItem
                    key={configSelectValue(config)}
                    value={configSelectValue(config)}
                    label={configName(config, t)}
                    className="text-xs"
                  >
                    {configName(config, t)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {videoConfigs.length === 0 ? (
              <p className="text-xs text-amber-500">{t("videos.noModel")}</p>
            ) : null}
          </div>

          {/* 视频分辨率与比例 */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-foreground/90">
                {t("videos.quality")}
              </label>
              <Select
                value={selectedQuality}
                onValueChange={(val) => setQuality(val as VideoQuality)}
              >
                <SelectTrigger className="h-9 text-xs">
                  <SelectValue>{selectedQuality}</SelectValue>
                </SelectTrigger>
                <SelectContent alignItemWithTrigger={false}>
                  {(capabilities?.qualities ?? ["720p"]).map((item) => (
                    <SelectItem key={item} value={item} className="text-xs">
                      {item}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-foreground/90">
                {t("videos.aspectRatio")}
              </label>
              <Select
                value={selectedAspectRatio}
                onValueChange={(val) => setAspectRatio(val as VideoAspectRatio)}
              >
                <SelectTrigger className="h-9 text-xs">
                  <SelectValue>{selectedAspectRatio}</SelectValue>
                </SelectTrigger>
                <SelectContent alignItemWithTrigger={false} className="max-h-60">
                  {(capabilities?.aspectRatios ?? ["16:9"]).map((item) => (
                    <SelectItem key={item} value={item} className="text-xs">
                      {item}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* 时长与 FPS */}
          <div className="grid grid-cols-2 gap-3">
            {durationOptions.length ? (
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-foreground/90">
                  {t("videos.duration")}
                </label>
                <Select
                  value={String(selectedDuration)}
                  onValueChange={(val) => setDuration(Number(val))}
                >
                  <SelectTrigger className="h-9 text-xs">
                    <SelectValue>{selectedDuration}s</SelectValue>
                  </SelectTrigger>
                  <SelectContent alignItemWithTrigger={false}>
                    {durationOptions.map((d) => (
                      <SelectItem key={d} value={String(d)} className="text-xs">
                        {d}s
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}

            {capabilities?.fps?.length ? (
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-foreground/90">FPS</label>
                <Select
                  value={String(selectedFps)}
                  onValueChange={(val) => setFps(Number(val) as VideoFps)}
                >
                  <SelectTrigger className="h-9 text-xs">
                    <SelectValue>{selectedFps} fps</SelectValue>
                  </SelectTrigger>
                  <SelectContent alignItemWithTrigger={false}>
                    {capabilities.fps.map((f) => (
                      <SelectItem key={f} value={String(f)} className="text-xs">
                        {f} fps
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}
          </div>

          {/* 提示词输入区 */}
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <label className="text-xs font-semibold text-foreground/90">
                {t("videos.prompt")}
              </label>
              <div className="flex items-center gap-1.5">
                <Select
                  value={promptLanguage}
                  onValueChange={(val) =>
                    setPromptLanguage((val ?? "auto") as "auto" | "zh" | "en")
                  }
                >
                  <SelectTrigger
                    className="h-7 w-20 text-[11px]"
                    aria-label={t("common.promptLanguage")}
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent alignItemWithTrigger={false}>
                    <SelectItem value="auto" className="text-xs">
                      {t("common.promptLanguageAuto")}
                    </SelectItem>
                    <SelectItem value="zh" className="text-xs">
                      {t("common.promptLanguageZh")}
                    </SelectItem>
                    <SelectItem value="en" className="text-xs">
                      {t("common.promptLanguageEn")}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <Button
                  type="button"
                  variant="outline"
                  size="xs"
                  disabled={!prompt.trim() || optimizeMutation.isPending}
                  onClick={() => optimizeMutation.mutate()}
                  className="h-7 text-[11px] gap-1 cursor-pointer"
                >
                  {optimizeMutation.isPending ? (
                    <Loader2 className="size-3 animate-spin text-primary" />
                  ) : (
                    <Sparkles className="size-3 text-primary" />
                  )}
                  {optimizeMutation.isPending
                    ? t("common.optimizingPrompt")
                    : t("common.optimizePrompt")}
                </Button>
              </div>
            </div>
            <Textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder={t("videos.promptPlaceholder")}
              className="min-h-24 rounded-xl text-xs resize-none"
            />
          </div>

          {capabilities?.referenceImages ? (
            <div className="space-y-2 rounded-2xl border border-border/70 bg-card/30 p-3">
              <div className="flex items-center justify-between gap-2 text-xs font-semibold">
                <div className="flex items-center gap-1.5">
                  <ImageIcon className="size-4 text-primary" />
                  <span>{t("videos.referenceImagesLabel")}</span>
                </div>
                <Badge variant="secondary" className="text-[10px]">{visibleReferences.length}/{capabilities.maxReferenceImages}</Badge>
              </div>
              <div className="flex items-center gap-1">
                {usesQwenTemporaryUpload ? (
                  <Button type="button" variant="secondary" size="xs" className="h-8 gap-1 text-xs" onClick={() => fileInputRef.current?.click()} disabled={visibleReferences.length >= capabilities.maxReferenceImages}>
                    <Upload className="size-3.5" />{t("videos.uploadReferenceImage")}
                  </Button>
                ) : null}
                <Button type="button" variant="ghost" size="xs" onClick={() => setReferences([])} disabled={!visibleReferences.length}>{t("common.clear")}</Button>
              </div>
              {usesQwenTemporaryUpload ? <input ref={fileInputRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(event) => { addReferences(event.target.files, "images"); event.currentTarget.value = ""; }} /> : null}
              <div className="flex gap-2">
                <Input value={referenceImageUrl} onChange={(event) => setReferenceImageUrl(event.target.value)} placeholder={t("videos.referenceUrlPlaceholder")} aria-label={t("videos.referenceImagesLabel")} className="h-8 text-xs" />
                <Button type="button" variant="secondary" size="xs" className="h-8 shrink-0 gap-1" onClick={() => addReferenceUrl("images")} disabled={visibleReferences.length >= capabilities.maxReferenceImages}><Plus className="size-3.5" />{t("videos.addReferenceUrl")}</Button>
              </div>
              <div className="space-y-1.5">
                {visibleReferences.map((reference, index) => (
                  <div key={`${reference.name || reference.url}-${index}`} className="flex items-center gap-2 rounded-lg border border-border/60 bg-background/60 p-1.5">
                    <Image src={reference.data || reference.url || ""} alt="" width={40} height={40} unoptimized className="size-10 shrink-0 rounded-md object-cover" />
                    <span className="min-w-0 flex-1 truncate text-xs">{reference.name || reference.url}</span>
                    <Button type="button" variant="ghost" size="icon-xs" onClick={() => setReferences((current) => current.filter((item) => item !== reference))} aria-label={t("common.delete")}><Trash2 className="size-3.5 text-destructive" /></Button>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {capabilities?.referenceVideo ? (
            <div className="space-y-2 rounded-2xl border border-border/70 bg-card/30 p-3">
              <div className="flex items-center justify-between gap-2 text-xs font-semibold"><div className="flex items-center gap-1.5"><Video className="size-4 text-primary" /><span>{t("videos.referenceVideo")}</span></div><Badge variant="secondary" className="text-[10px]">{visibleReferenceVideos.length}/{capabilities.maxReferenceVideos}</Badge></div>
              <div className="flex items-center gap-1">{usesQwenTemporaryUpload ? <><Button type="button" variant="secondary" size="xs" className="h-8 gap-1 text-xs" onClick={() => videoInputRef.current?.click()} disabled={visibleReferenceVideos.length >= capabilities.maxReferenceVideos}><Upload className="size-3.5" />{t("videos.uploadReferenceVideo")}</Button><input ref={videoInputRef} type="file" accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm" multiple={capabilities.maxReferenceVideos > 1} className="hidden" onChange={(event) => { addReferences(event.target.files, "videos"); event.currentTarget.value = ""; }} /></> : null}<Button type="button" variant="ghost" size="xs" onClick={() => setReferenceVideos([])} disabled={!visibleReferenceVideos.length}>{t("common.clear")}</Button></div>
              <div className="flex gap-2"><Input value={referenceVideoUrl} onChange={(event) => setReferenceVideoUrl(event.target.value)} placeholder={t("videos.referenceUrlPlaceholder")} aria-label={t("videos.referenceVideo")} className="h-8 text-xs" /><Button type="button" variant="secondary" size="xs" className="h-8 shrink-0 gap-1" onClick={() => addReferenceUrl("videos")} disabled={visibleReferenceVideos.length >= capabilities.maxReferenceVideos}><Plus className="size-3.5" />{t("videos.addReferenceUrl")}</Button></div>
              <div className="space-y-1.5">{visibleReferenceVideos.map((reference, index) => <div key={`${reference.name || reference.url}-${index}`} className="flex items-center gap-2"><Input value={reference.name || reference.url || ""} readOnly className="h-8 text-xs" /><Button type="button" variant="ghost" size="icon-xs" onClick={() => setReferenceVideos((current) => current.filter((item) => item !== reference))} aria-label={t("common.delete")}><Trash2 className="size-3.5 text-destructive" /></Button></div>)}</div>
            </div>
          ) : null}

          {capabilities?.referenceAudio ? (
            <div className="space-y-2 rounded-2xl border border-border/70 bg-card/30 p-3">
              <div className="flex items-center justify-between gap-2 text-xs font-semibold"><div className="flex items-center gap-1.5"><AudioLines className="size-4 text-primary" /><span>{t("videos.referenceAudio")}</span></div><Badge variant="secondary" className="text-[10px]">{visibleReferenceAudios.length}/{capabilities.maxReferenceAudios}</Badge></div>
              <div className="flex items-center gap-1">{usesQwenTemporaryUpload ? <><Button type="button" variant="secondary" size="xs" className="h-8 gap-1 text-xs" onClick={() => audioInputRef.current?.click()} disabled={visibleReferenceAudios.length >= capabilities.maxReferenceAudios}><Upload className="size-3.5" />{t("videos.uploadReferenceAudio")}</Button><input ref={audioInputRef} type="file" accept="audio/mpeg,audio/wav,audio/x-wav,audio/mp4,.mp3,.wav,.m4a" multiple={capabilities.maxReferenceAudios > 1} className="hidden" onChange={(event) => { addReferences(event.target.files, "audios"); event.currentTarget.value = ""; }} /></> : null}<Button type="button" variant="ghost" size="xs" onClick={() => setReferenceAudios([])} disabled={!visibleReferenceAudios.length}>{t("common.clear")}</Button></div>
              <div className="flex gap-2"><Input value={referenceAudioUrl} onChange={(event) => setReferenceAudioUrl(event.target.value)} placeholder={t("videos.referenceUrlPlaceholder")} aria-label={t("videos.referenceAudio")} className="h-8 text-xs" /><Button type="button" variant="secondary" size="xs" className="h-8 shrink-0 gap-1" onClick={() => addReferenceUrl("audios")} disabled={visibleReferenceAudios.length >= capabilities.maxReferenceAudios}><Plus className="size-3.5" />{t("videos.addReferenceUrl")}</Button></div>
              <div className="space-y-1.5">{visibleReferenceAudios.map((reference, index) => <div key={`${reference.name || reference.url}-${index}`} className="flex items-center gap-2"><Input value={reference.name || reference.url || ""} readOnly className="h-8 text-xs" /><Button type="button" variant="ghost" size="icon-xs" onClick={() => setReferenceAudios((current) => current.filter((item) => item !== reference))} aria-label={t("common.delete")}><Trash2 className="size-3.5 text-destructive" /></Button></div>)}</div>
            </div>
          ) : null}
        </div>

        {/* 历史生成 */}
        <div className="mt-3 border-t border-border/70 pt-3">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-semibold">
              <History className="size-3.5 text-muted-foreground" />
              <span>{t("videos.history")}</span>
            </div>
            <Badge variant="outline" className="text-[10px]">
              {history.length}
            </Badge>
          </div>
          {history.length ? (
            <div className="max-h-36 space-y-1.5 overflow-y-auto pr-1 chat-message-list-scrollbar">
              {history.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setVideoUrl(item.videoUrl)}
                  className="flex w-full items-center gap-2 rounded-xl border border-border/60 bg-card/60 p-2 text-left transition-all hover:border-primary/40 hover:bg-card cursor-pointer"
                >
                  <Film className="size-4 shrink-0 text-primary" />
                  <span className="min-w-0 flex-1 truncate text-xs font-medium text-foreground">
                    {item.prompt}
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    {formatDateTime(item.createdAt)}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="text-center py-2 text-[11px] text-muted-foreground">
              {t("videos.historyEmpty")}
            </p>
          )}
        </div>

        {/* 立即生成主按钮 */}
        <div className="mt-3 border-t border-border/70 pt-3">
          <Button
            className="h-10 w-full gap-2 rounded-xl font-bold shadow-md cursor-pointer transition-all active:scale-[0.99]"
            onClick={generate}
            disabled={!prompt.trim() || !selectedConfig || generateMutation.isPending}
          >
            <Sparkles className="size-4" />
            {generateMutation.isPending ? generatingLabel : t("videos.generateNow")}
          </Button>
        </div>
      </aside>

      {/* 右侧：视频监视播放区 */}
      <section className="flex min-h-0 min-w-0 flex-col p-4 md:p-6">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-bold tracking-tight text-foreground">
              {t("videos.preview")}
            </h2>
            {videoUrl ? (
              <Badge variant="default" className="text-[10px]">
                Video Ready
              </Badge>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="h-8 gap-1.5 text-xs cursor-pointer"
              onClick={generate}
              disabled={!videoUrl || generateMutation.isPending}
            >
              <RotateCcw className="size-3.5" />
              {t("videos.regenerate")}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              className="h-8 gap-1.5 text-xs cursor-pointer font-semibold shadow-xs"
              onClick={downloadVideo}
              disabled={!videoUrl || isDownloading}
            >
              <Download className="size-3.5" />
              {t("videos.download")}
            </Button>
          </div>
        </div>

        {/* 视频渲染视窗 */}
        <div className="mt-4 flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-3xl border border-border/80 bg-card/20 p-4 shadow-inner backdrop-blur-md relative dark:bg-black/20">
          <div className="pointer-events-none absolute inset-0 bg-grid-dots opacity-20" />

          {generateMutation.isPending ? (
            <div className="relative z-10 text-center">
              <div className="relative mx-auto mb-4 flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <Film className="size-7 animate-pulse" />
                <span className="absolute inset-0 size-14 animate-ping rounded-2xl bg-primary/20 opacity-40" />
              </div>
              <p className="text-sm font-semibold text-foreground">{generatingLabel}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                正在进行视频神经渲染与动作物理模拟...
              </p>
            </div>
          ) : videoUrl ? (
            <div className="relative z-10 flex h-full w-full items-center justify-center animate-in fade-in-0 duration-300">
              <video
                src={resolvedVideoUrl}
                controls
                autoPlay
                loop
                className="max-h-full max-w-full rounded-2xl shadow-2xl"
              />
            </div>
          ) : (
            <div className="relative z-10 text-center">
              <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-2xl bg-muted/60 text-muted-foreground">
                <Video className="size-6" />
              </div>
              <p className="text-sm font-semibold text-foreground">{t("videos.emptyPreview")}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                在左侧配置参数与提示词，即可渲染高质量动态视频
              </p>
            </div>
          )}
        </div>

        {errorMessage ? (
          <div className="mt-3 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
            {errorMessage}
          </div>
        ) : null}
      </section>
    </div>
  );
}
