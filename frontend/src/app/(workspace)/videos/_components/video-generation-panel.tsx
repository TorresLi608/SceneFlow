"use client";

import { useMutation } from "@tanstack/react-query";
import {
  AudioLines,
  Check,
  Copy,
  Download,
  Film,
  History,
  ImageIcon,
  Maximize2,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  RotateCcw,
  Sparkles,
  Square,
  Trash2,
  Upload,
  Video,
} from "lucide-react";
import Image from "next/image";
import { useEffect, useMemo, useRef, useState } from "react";

import { generateVideoAction } from "@/actions/video-generation-actions";
import { isCancel } from "axios";
import { optimizePromptAction } from "@/actions/prompt-actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { cn } from "@/lib/utils";
import type { UserConfig } from "@/types/auth";
import type {
  VideoAspectRatio,
  VideoFps,
  VideoQuality,
  VideoReferenceInput,
  GenerateVideoInput,
} from "@/types/video-generation";

const historyStorageKey = "sceneflow-video-generation-history-v1";
type AssetTab = "images" | "videos" | "audios";

interface VideoHistoryItem {
  id: string;
  videoUrl: string;
  prompt: string;
  quality?: string;
  aspectRatio?: string;
  duration?: number;
  fps?: number;
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

function readVideoHistory(): VideoHistoryItem[] {
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
  const promptExtend = false;
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
  const requestController = useRef<AbortController | null>(null);
  const optimizeController = useRef<AbortController | null>(null);

  const stopOptimize = () => {
    optimizeController.current?.abort();
    optimizeController.current = null;
    optimizeMutation.reset();
  };

  const startOptimize = () => {
    optimizeController.current = new AbortController();
    optimizeMutation.mutate();
  };

  // 多模态参考素材 Tab
  const [activeAssetTab, setActiveAssetTab] = useState<AssetTab>("images");

  // 视频全屏预览 Dialog
  const [modalOpen, setModalOpen] = useState(false);
  const [showModalSidebar, setShowModalSidebar] = useState(true);
  const [modalItem, setModalItem] = useState<{
    url: string;
    prompt: string;
    quality?: string;
    aspectRatio?: string;
    duration?: number;
    fps?: number;
  } | null>(null);
  const [copied, setCopied] = useState(false);

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

  const hasAnyReferenceCapabilities = Boolean(
    capabilities?.referenceImages || capabilities?.referenceVideo || capabilities?.referenceAudio
  );

  const generateMutation = useMutation({
    mutationFn: (payload: GenerateVideoInput) => generateVideoAction(payload, requestController.current?.signal),
    onSuccess: (response, variables) => {
      const item: VideoHistoryItem = {
        id: `${Date.now()}`,
        videoUrl: response.video.url,
        prompt: variables.prompt,
        quality: variables.quality,
        aspectRatio: variables.aspectRatio,
        duration: variables.duration,
        fps: variables.fps,
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
    onError: (error) => {
      if (isCancel(error)) return;
      setErrorMessage(resolveRequestError(error, t("videos.generateFailed")));
    },
    onSettled: () => { requestController.current = null; },
  });

  const optimizeMutation = useMutation({
    mutationFn: () =>
      optimizePromptAction(
        {
          kind: "video",
          prompt: prompt.trim(),
          context: {
            outputLanguage: promptLanguage,
            aspectRatio: selectedAspectRatio,
            quality: selectedQuality,
            duration: selectedDuration,
          },
        },
        optimizeController.current?.signal
      ),
    onSuccess: (response) => {
      setPrompt(response.prompt);
      setErrorMessage(null);
    },
    onError: (error) => {
      if (isCancel(error)) return;
      setErrorMessage(resolveRequestError(error, t("common.optimizePromptFailed")));
    },
    onSettled: () => {
      optimizeController.current = null;
    },
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
    requestController.current = new AbortController();
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

  const stopGeneration = () => {
    requestController.current?.abort();
    requestController.current = null;
    generateMutation.reset();
  };

  const deleteHistory = (id: string) => {
    setHistory((current) => {
      const next = current.filter((item) => item.id !== id);
      saveVideoHistory(next);
      return next;
    });
  };

  const downloadVideo = async (urlToDownload?: string) => {
    const targetUrl = urlToDownload || resolvedVideoUrl;
    if (!targetUrl || isDownloading) return;
    setIsDownloading(true);
    setErrorMessage(null);
    try {
      const response = await fetch(targetUrl);
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

  const copyPrompt = (textToCopy: string) => {
    if (!textToCopy) return;
    navigator.clipboard.writeText(textToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const openVideoModal = (
    url: string,
    p: string,
    q?: string,
    ar?: string,
    d?: number,
    f?: number
  ) => {
    setModalItem({ url, prompt: p, quality: q, aspectRatio: ar, duration: d, fps: f });
    setModalOpen(true);
  };

  const generatingLabel = t("videos.generatingVideoWithSeconds", {
    seconds: elapsedSeconds,
  });

  return (
    <div className="grid min-h-0 flex-1 bg-background lg:grid-cols-[380px_minmax(0,1fr)]">
      {/* 左侧控制侧边栏 */}
      <aside className="flex min-h-0 flex-col border-b border-border/70 bg-card/40 p-4 backdrop-blur-xl lg:border-r lg:border-b-0 lg:p-5">
        {/* 顶部标题栏 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Video className="size-4" />
            </div>
            <h2 className="text-sm font-bold tracking-tight text-foreground">
              {t("home.videos")}
            </h2>
          </div>
          <Badge variant="secondary" className="text-[10px] font-semibold tracking-wide">
            AI VIDEO STUDIO
          </Badge>
        </div>

        {/* 侧边栏滚动控制区 */}
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
              <SelectTrigger className="h-9 w-full text-xs">
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

          {/* 视频分辨率与画面比例 */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-foreground/90">
                {t("videos.quality")}
              </label>
              <Select
                value={selectedQuality}
                onValueChange={(val) => setQuality(val as VideoQuality)}
              >
                <SelectTrigger className="h-9 w-full text-xs">
                  <SelectValue>{selectedQuality}</SelectValue>
                </SelectTrigger>
                <SelectContent alignItemWithTrigger={false}>
                  {(capabilities?.qualities ?? ["720p"]).map((item) => (
                    <SelectItem key={item} value={item} label={item} className="text-xs">
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
                <SelectTrigger className="h-9 w-full text-xs">
                  <SelectValue>{selectedAspectRatio}</SelectValue>
                </SelectTrigger>
                <SelectContent alignItemWithTrigger={false} className="max-h-60">
                  {(capabilities?.aspectRatios ?? ["16:9"]).map((item) => (
                    <SelectItem key={item} value={item} label={item} className="text-xs">
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
                  <SelectTrigger className="h-9 w-full text-xs">
                    <SelectValue>{selectedDuration}s</SelectValue>
                  </SelectTrigger>
                  <SelectContent alignItemWithTrigger={false}>
                    {durationOptions.map((d) => (
                      <SelectItem key={d} value={String(d)} label={`${d}s`} className="text-xs">
                        {d}s
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}

            {capabilities?.fps?.length ? (
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-foreground/90">
                  {t("videos.fps")}
                </label>
                <Select
                  value={String(selectedFps)}
                  onValueChange={(val) => setFps(Number(val) as VideoFps)}
                >
                  <SelectTrigger className="h-9 w-full text-xs">
                    <SelectValue>{selectedFps} fps</SelectValue>
                  </SelectTrigger>
                  <SelectContent alignItemWithTrigger={false}>
                    {capabilities.fps.map((f) => (
                      <SelectItem key={f} value={String(f)} label={`${f} fps`} className="text-xs">
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
                    <SelectItem value="auto" label={t("common.promptLanguageAuto")} className="text-xs">
                      {t("common.promptLanguageAuto")}
                    </SelectItem>
                    <SelectItem value="zh" label={t("common.promptLanguageZh")} className="text-xs">
                      {t("common.promptLanguageZh")}
                    </SelectItem>
                    <SelectItem value="en" label={t("common.promptLanguageEn")} className="text-xs">
                      {t("common.promptLanguageEn")}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <Button
                  type="button"
                  variant={optimizeMutation.isPending ? "destructive" : "outline"}
                  size="xs"
                  disabled={!prompt.trim() && !optimizeMutation.isPending}
                  onClick={optimizeMutation.isPending ? stopOptimize : startOptimize}
                  className={cn(
                    "h-7 gap-1 text-[11px] cursor-pointer transition-colors",
                    optimizeMutation.isPending && "animate-pulse font-medium"
                  )}
                  title={
                    optimizeMutation.isPending
                      ? t("common.stopOptimizePrompt")
                      : t("common.optimizePrompt")
                  }
                >
                  {optimizeMutation.isPending ? (
                    <Square className="size-2.5 fill-current" />
                  ) : (
                    <Sparkles className="size-3 text-primary" />
                  )}
                  {optimizeMutation.isPending
                    ? t("common.stopOptimizePrompt")
                    : t("common.optimizePrompt")}
                </Button>
              </div>
            </div>
            <Textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder={t("videos.promptPlaceholder")}
              className="min-h-28 resize-none rounded-xl text-xs"
            />
          </div>

          {/* 多模态参考素材一体化卡片 */}
          {hasAnyReferenceCapabilities ? (
            <div className="space-y-3 rounded-2xl border border-border/70 bg-card/30 p-3.5">
              <div className="flex items-center justify-between gap-2">
                <label className="text-xs font-semibold text-foreground/90">
                  {t("videos.inputMedia")}
                </label>
                <Badge variant="secondary" className="text-[10px]">
                  {visibleReferences.length + visibleReferenceVideos.length + visibleReferenceAudios.length > 0
                    ? t("videos.videoToVideo")
                    : t("videos.textToVideo")}
                </Badge>
              </div>

              {/* 多模态素材 Tab 切换 */}
              <div className="grid grid-cols-3 gap-1 rounded-xl bg-muted/60 p-1">
                {capabilities?.referenceImages ? (
                  <button
                    type="button"
                    onClick={() => setActiveAssetTab("images")}
                    className={cn(
                      "flex h-7 items-center justify-center gap-1 rounded-lg text-[11px] font-medium transition-all cursor-pointer",
                      activeAssetTab === "images"
                        ? "bg-background text-foreground shadow-xs font-semibold"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    <ImageIcon className="size-3 text-primary" />
                    <span>图片</span>
                    {visibleReferences.length > 0 ? (
                      <span className="rounded-full bg-primary/15 px-1 text-[9px] text-primary">
                        {visibleReferences.length}
                      </span>
                    ) : null}
                  </button>
                ) : null}

                {capabilities?.referenceVideo ? (
                  <button
                    type="button"
                    onClick={() => setActiveAssetTab("videos")}
                    className={cn(
                      "flex h-7 items-center justify-center gap-1 rounded-lg text-[11px] font-medium transition-all cursor-pointer",
                      activeAssetTab === "videos"
                        ? "bg-background text-foreground shadow-xs font-semibold"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    <Video className="size-3 text-primary" />
                    <span>视频</span>
                    {visibleReferenceVideos.length > 0 ? (
                      <span className="rounded-full bg-primary/15 px-1 text-[9px] text-primary">
                        {visibleReferenceVideos.length}
                      </span>
                    ) : null}
                  </button>
                ) : null}

                {capabilities?.referenceAudio ? (
                  <button
                    type="button"
                    onClick={() => setActiveAssetTab("audios")}
                    className={cn(
                      "flex h-7 items-center justify-center gap-1 rounded-lg text-[11px] font-medium transition-all cursor-pointer",
                      activeAssetTab === "audios"
                        ? "bg-background text-foreground shadow-xs font-semibold"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    <AudioLines className="size-3 text-primary" />
                    <span>音频</span>
                    {visibleReferenceAudios.length > 0 ? (
                      <span className="rounded-full bg-primary/15 px-1 text-[9px] text-primary">
                        {visibleReferenceAudios.length}
                      </span>
                    ) : null}
                  </button>
                ) : null}
              </div>

              {/* 参考图片 Tab 详情 */}
              {activeAssetTab === "images" && capabilities?.referenceImages ? (
                <div className="space-y-2.5 pt-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground text-[11px]">
                      {t("video.limitImages", { count: capabilities.maxReferenceImages })}
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="xs"
                      onClick={() => setReferences([])}
                      disabled={!visibleReferences.length}
                      className="h-6 text-[11px]"
                    >
                      {t("videos.clearReferences")}
                    </Button>
                  </div>

                  {usesQwenTemporaryUpload ? (
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      className="h-8 w-full gap-1.5 text-xs font-medium cursor-pointer shadow-2xs"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={visibleReferences.length >= capabilities.maxReferenceImages}
                    >
                      <Upload className="size-3.5" />
                      {t("videos.uploadReferenceImage")}
                    </Button>
                  ) : null}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    className="hidden"
                    onChange={(event) => {
                      addReferences(event.target.files, "images");
                      event.currentTarget.value = "";
                    }}
                  />

                  <div className="flex gap-1.5">
                    <Input
                      value={referenceImageUrl}
                      onChange={(event) => setReferenceImageUrl(event.target.value)}
                      placeholder={t("videos.referenceUrlPlaceholder")}
                      aria-label={t("videos.referenceImagesLabel")}
                      className="h-8 text-xs"
                    />
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      className="h-8 shrink-0 gap-1 text-xs cursor-pointer font-medium"
                      onClick={() => addReferenceUrl("images")}
                      disabled={visibleReferences.length >= capabilities.maxReferenceImages}
                    >
                      <Plus className="size-3.5" />
                      {t("videos.addReferenceUrl")}
                    </Button>
                  </div>

                  {visibleReferences.length > 0 ? (
                    <div className="space-y-1.5 pt-1">
                      {visibleReferences.map((reference, index) => (
                        <div
                          key={`${reference.name || reference.url}-${index}`}
                          className="flex items-center gap-2 rounded-xl border border-border/60 bg-background/60 p-1.5"
                        >
                          <Image
                            src={reference.data || reference.url || ""}
                            alt=""
                            width={36}
                            height={36}
                            unoptimized
                            className="size-9 shrink-0 rounded-lg object-cover border border-border/50"
                          />
                          <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                            {reference.name || reference.url}
                          </span>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-xs"
                            onClick={() =>
                              setReferences((current) =>
                                current.filter((item) => item !== reference)
                              )
                            }
                            aria-label={t("common.delete")}
                            className="text-muted-foreground hover:text-destructive"
                          >
                            <Trash2 className="size-3.5" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}

              {/* 参考视频 Tab 详情 */}
              {activeAssetTab === "videos" && capabilities?.referenceVideo ? (
                <div className="space-y-2.5 pt-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground text-[11px]">
                      {t("video.limitVideos", { count: capabilities.maxReferenceVideos })}
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="xs"
                      onClick={() => setReferenceVideos([])}
                      disabled={!visibleReferenceVideos.length}
                      className="h-6 text-[11px]"
                    >
                      {t("videos.clearReferenceVideos")}
                    </Button>
                  </div>

                  {usesQwenTemporaryUpload ? (
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      className="h-8 w-full gap-1.5 text-xs font-medium cursor-pointer shadow-2xs"
                      onClick={() => videoInputRef.current?.click()}
                      disabled={visibleReferenceVideos.length >= capabilities.maxReferenceVideos}
                    >
                      <Upload className="size-3.5" />
                      {t("videos.uploadReferenceVideo")}
                    </Button>
                  ) : null}
                  <input
                    ref={videoInputRef}
                    type="file"
                    accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm"
                    multiple={capabilities.maxReferenceVideos > 1}
                    className="hidden"
                    onChange={(event) => {
                      addReferences(event.target.files, "videos");
                      event.currentTarget.value = "";
                    }}
                  />

                  <div className="flex gap-1.5">
                    <Input
                      value={referenceVideoUrl}
                      onChange={(event) => setReferenceVideoUrl(event.target.value)}
                      placeholder={t("videos.referenceUrlPlaceholder")}
                      aria-label={t("videos.referenceVideo")}
                      className="h-8 text-xs"
                    />
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      className="h-8 shrink-0 gap-1 text-xs cursor-pointer font-medium"
                      onClick={() => addReferenceUrl("videos")}
                      disabled={visibleReferenceVideos.length >= capabilities.maxReferenceVideos}
                    >
                      <Plus className="size-3.5" />
                      {t("videos.addReferenceUrl")}
                    </Button>
                  </div>

                  {visibleReferenceVideos.length > 0 ? (
                    <div className="space-y-1.5 pt-1">
                      {visibleReferenceVideos.map((reference, index) => (
                        <div
                          key={`${reference.name || reference.url}-${index}`}
                          className="flex items-center gap-2 rounded-xl border border-border/60 bg-background/60 p-2"
                        >
                          <Video className="size-4 shrink-0 text-primary" />
                          <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                            {reference.name || reference.url}
                          </span>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-xs"
                            onClick={() =>
                              setReferenceVideos((current) =>
                                current.filter((item) => item !== reference)
                              )
                            }
                            aria-label={t("common.delete")}
                            className="text-muted-foreground hover:text-destructive"
                          >
                            <Trash2 className="size-3.5" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}

              {/* 参考音频 Tab 详情 */}
              {activeAssetTab === "audios" && capabilities?.referenceAudio ? (
                <div className="space-y-2.5 pt-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground text-[11px]">
                      {t("video.limitAudios", { count: capabilities.maxReferenceAudios })}
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="xs"
                      onClick={() => setReferenceAudios([])}
                      disabled={!visibleReferenceAudios.length}
                      className="h-6 text-[11px]"
                    >
                      {t("videos.clearReferenceAudios")}
                    </Button>
                  </div>

                  {usesQwenTemporaryUpload ? (
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      className="h-8 w-full gap-1.5 text-xs font-medium cursor-pointer shadow-2xs"
                      onClick={() => audioInputRef.current?.click()}
                      disabled={visibleReferenceAudios.length >= capabilities.maxReferenceAudios}
                    >
                      <Upload className="size-3.5" />
                      {t("videos.uploadReferenceAudio")}
                    </Button>
                  ) : null}
                  <input
                    ref={audioInputRef}
                    type="file"
                    accept="audio/mpeg,audio/wav,audio/x-wav,audio/mp4,.mp3,.wav,.m4a"
                    multiple={capabilities.maxReferenceAudios > 1}
                    className="hidden"
                    onChange={(event) => {
                      addReferences(event.target.files, "audios");
                      event.currentTarget.value = "";
                    }}
                  />

                  <div className="flex gap-1.5">
                    <Input
                      value={referenceAudioUrl}
                      onChange={(event) => setReferenceAudioUrl(event.target.value)}
                      placeholder={t("videos.referenceUrlPlaceholder")}
                      aria-label={t("videos.referenceAudio")}
                      className="h-8 text-xs"
                    />
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      className="h-8 shrink-0 gap-1 text-xs cursor-pointer font-medium"
                      onClick={() => addReferenceUrl("audios")}
                      disabled={visibleReferenceAudios.length >= capabilities.maxReferenceAudios}
                    >
                      <Plus className="size-3.5" />
                      {t("videos.addReferenceUrl")}
                    </Button>
                  </div>

                  {visibleReferenceAudios.length > 0 ? (
                    <div className="space-y-1.5 pt-1">
                      {visibleReferenceAudios.map((reference, index) => (
                        <div
                          key={`${reference.name || reference.url}-${index}`}
                          className="flex items-center gap-2 rounded-xl border border-border/60 bg-background/60 p-2"
                        >
                          <AudioLines className="size-4 shrink-0 text-primary" />
                          <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                            {reference.name || reference.url}
                          </span>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-xs"
                            onClick={() =>
                              setReferenceAudios((current) =>
                                current.filter((item) => item !== reference)
                              )
                            }
                            aria-label={t("common.delete")}
                            className="text-muted-foreground hover:text-destructive"
                          >
                            <Trash2 className="size-3.5" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        {/* 历史生成记录 */}
        <div className="mt-3 border-t border-border/70 pt-3">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground/90">
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
                <div key={item.id} className="flex w-full items-center gap-1 rounded-xl border border-border/60 bg-card/60 p-2 transition-all hover:border-primary/40 hover:bg-card">
                  <button
                    type="button"
                    onClick={() => { setVideoUrl(item.videoUrl); setPrompt(item.prompt); }}
                    className="flex min-w-0 flex-1 items-center gap-2 text-left cursor-pointer"
                  >
                    <Film className="size-4 shrink-0 text-primary" />
                    <span className="min-w-0 flex-1 truncate text-xs font-medium text-foreground">
                      {item.prompt}
                    </span>
                    <span className="text-[10px] text-muted-foreground shrink-0">
                      {formatDateTime(item.createdAt)}
                    </span>
                  </button>
                  <Button type="button" variant="ghost" size="icon-xs" onClick={() => deleteHistory(item.id)} aria-label={t("videos.deleteHistory")} className="shrink-0 text-muted-foreground hover:text-destructive">
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <p className="py-2 text-center text-[11px] text-muted-foreground">
              {t("videos.historyEmpty")}
            </p>
          )}
        </div>

        {/* 立即生成主按钮 */}
        <div className="mt-3 border-t border-border/70 pt-3">
          {generateMutation.isPending ? (
            <Button variant="destructive" className="h-10 w-full gap-2 rounded-xl font-bold" onClick={stopGeneration}>
              <Square className="size-3.5 fill-current" />
              {t("common.stopGeneration")}
            </Button>
          ) : <Button
            className="h-10 w-full gap-2 rounded-xl font-bold shadow-md cursor-pointer transition-all active:scale-[0.99]"
            onClick={generate}
            disabled={!prompt.trim() || !selectedConfig || generateMutation.isPending}
          >
            <Sparkles className="size-4" />
            <Sparkles className="size-4" />
            {t("videos.generateNow")}
          </Button>}
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
                Ready · {selectedQuality} · {selectedAspectRatio}
              </Badge>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            {videoUrl ? (
              <Button
                variant="outline"
                size="sm"
                className="h-8 gap-1.5 text-xs cursor-pointer"
                onClick={() =>
                  openVideoModal(
                    resolvedVideoUrl,
                    prompt,
                    selectedQuality,
                    selectedAspectRatio,
                    selectedDuration,
                    selectedFps
                  )
                }
              >
                <Maximize2 className="size-3.5" />
                全屏播放
              </Button>
            ) : null}
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
              onClick={() => downloadVideo()}
              disabled={!videoUrl || isDownloading}
            >
              <Download className="size-3.5" />
              {t("videos.download")}
            </Button>
          </div>
        </div>

        {/* 视频渲染视窗 */}
        <div className="relative mt-4 flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-3xl border border-border/80 bg-card/20 p-4 shadow-inner backdrop-blur-md dark:bg-black/20">
          <div className="pointer-events-none absolute inset-0 bg-grid-dots opacity-20" />

          {generateMutation.isPending ? (
            <div className="relative z-10 text-center space-y-4">
              <div className="relative mx-auto flex size-16 items-center justify-center rounded-2xl bg-primary/10 text-primary shadow-xs">
                <Film className="size-8 animate-pulse" />
                <span className="absolute inset-0 size-16 animate-ping rounded-2xl bg-primary/20 opacity-40" />
              </div>
              <div>
                <p className="text-sm font-bold text-foreground">{generatingLabel}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {t("videos.generatingHint")}
                </p>
              </div>
              {/* 动态视频进度条微动效 */}
              <div className="mx-auto flex w-48 items-center justify-center gap-1">
                {[60, 90, 45, 100, 70, 85, 50, 95].map((h, i) => (
                  <span
                    key={i}
                    className="w-1.5 rounded-full bg-primary/60 animate-pulse"
                    style={{
                      height: `${h * 0.25}px`,
                      animationDelay: `${i * 150}ms`,
                      animationDuration: "1s",
                    }}
                  />
                ))}
              </div>
            </div>
          ) : videoUrl ? (
            <div className="relative z-10 flex h-full w-full items-center justify-center animate-in fade-in-0 duration-300">
              <video
                src={resolvedVideoUrl}
                controls
                autoPlay
                loop
                className="max-h-full max-w-full rounded-2xl shadow-2xl border border-border/60"
              />
            </div>
          ) : (
            <div className="relative z-10 text-center space-y-2">
              <div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-muted/60 text-muted-foreground shadow-xs">
                <Video className="size-7" />
              </div>
              <p className="text-sm font-semibold text-foreground">{t("videos.emptyPreview")}</p>
              <p className="max-w-xs text-xs text-muted-foreground">
                {t("videos.emptyPreviewHint")}
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

      {/* 视频详情与全屏播放 Dialog（大屏沉浸式视窗） */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="w-[98vw] max-w-[1850px] h-[95vh] max-h-[96vh] flex flex-col p-0 overflow-hidden gap-0 rounded-2xl border border-border/80 shadow-2xl bg-background">
          <DialogHeader className="p-3.5 px-5 border-b border-border/70 flex flex-row items-center justify-between bg-card/40 shrink-0">
            <div className="flex items-center gap-3">
              <div className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Film className="size-4" />
              </div>
              <div className="space-y-0.5">
                <DialogTitle className="text-sm font-bold flex items-center gap-2">
                  {t("videos.modalTitle")}
                </DialogTitle>
                <DialogDescription className="text-xs">
                  {t("videos.modalDesc")}
                </DialogDescription>
              </div>
            </div>

            <div className="flex items-center gap-2 pr-8">
              <Button
                variant="outline"
                size="sm"
                className="h-8 gap-1.5 text-xs font-medium cursor-pointer"
                onClick={() => setShowModalSidebar((prev) => !prev)}
                title={showModalSidebar ? t("videos.pureViewTitle") : t("videos.showParamsTitle")}
              >
                {showModalSidebar ? (
                  <>
                    <PanelRightClose className="size-3.5" />
                    <span>{t("videos.pureView")}</span>
                  </>
                ) : (
                  <>
                    <PanelRightOpen className="size-3.5" />
                    <span>{t("videos.showParams")}</span>
                  </>
                )}
              </Button>
            </div>
          </DialogHeader>

          {modalItem ? (
            <div className="flex flex-col md:flex-row flex-1 min-h-0 bg-background/50 overflow-hidden">
              {/* 大屏播放器主视窗：深色暗影影院背景 */}
              <div className="relative flex-1 min-w-0 h-full flex items-center justify-center bg-black/95 dark:bg-black p-2 sm:p-4 overflow-hidden min-h-0">
                <div className="pointer-events-none absolute inset-0 bg-grid-dots opacity-10" />
                <video
                  src={modalItem.url}
                  controls
                  autoPlay
                  loop
                  className="max-h-full max-w-full rounded-2xl shadow-2xl object-contain border border-white/10"
                />
              </div>

              {/* 右侧参数与提示词面板 */}
              {showModalSidebar ? (
                <div className="w-full md:w-80 lg:w-96 flex flex-col justify-between shrink-0 border-t md:border-t-0 md:border-l border-border/70 bg-card/60 p-5 space-y-4 overflow-y-auto chat-message-list-scrollbar animate-in slide-in-from-right-4 duration-200">
                  <div className="space-y-4">
                    <div className="space-y-1.5">
                      <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block">
                        {t("videos.specsTitle")}
                      </span>
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {modalItem.quality ? (
                          <Badge variant="secondary" className="text-xs font-semibold px-2 py-0.5">
                            {modalItem.quality}
                          </Badge>
                        ) : null}
                        {modalItem.aspectRatio ? (
                          <Badge variant="outline" className="text-xs font-medium px-2 py-0.5">
                            {t("videos.ratioLabel", { ratio: modalItem.aspectRatio })}
                          </Badge>
                        ) : null}
                        {modalItem.duration ? (
                          <Badge variant="outline" className="text-xs font-medium px-2 py-0.5">
                            {modalItem.duration}s
                          </Badge>
                        ) : null}
                        {modalItem.fps ? (
                          <Badge variant="outline" className="text-xs font-medium px-2 py-0.5">
                            {modalItem.fps} FPS
                          </Badge>
                        ) : null}
                        <Badge variant="outline" className="text-xs font-medium px-2 py-0.5">
                          MP4 H.264
                        </Badge>
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block">
                        {t("videos.promptTitle")}
                      </label>
                      <div className="rounded-2xl border border-border/70 bg-muted/40 p-3.5 text-xs leading-relaxed max-h-72 overflow-y-auto text-foreground whitespace-pre-wrap font-mono chat-message-list-scrollbar">
                        {modalItem.prompt}
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2.5 pt-3 border-t border-border/70 shrink-0">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-10 w-full gap-2 text-xs font-medium cursor-pointer shadow-2xs"
                      onClick={() => copyPrompt(modalItem.prompt)}
                    >
                      {copied ? (
                        <Check className="size-4 text-emerald-500" />
                      ) : (
                        <Copy className="size-4" />
                      )}
                      {copied ? t("videos.copiedPrompt") : t("videos.copyPrompt")}
                    </Button>
                    <Button
                      size="sm"
                      className="h-10 w-full gap-2 text-xs font-bold cursor-pointer shadow-sm"
                      onClick={() => downloadVideo(modalItem.url)}
                    >
                      <Download className="size-4" />
                      {t("videos.downloadFull")}
                    </Button>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
