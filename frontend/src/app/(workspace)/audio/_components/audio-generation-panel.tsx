"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AudioLines,
  Check,
  Download,
  History,
  Loader2,
  Mic,
  Music,
  Plus,
  RotateCcw,
  Sparkles,
  User,
  Volume2,
  Wand2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  designVoiceAction,
  generateAudioAction,
  listUserVoicesAction,
  saveVoiceAction,
} from "@/actions/audio-generation-actions";
import { optimizePromptAction } from "@/actions/prompt-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
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
import type { GenerateAudioInput, UserVoice } from "@/types/audio-generation";

const historyStorageKey = "sceneflow-audio-generation-history-v2";
type VoiceSource = "builtin" | "custom";

interface AudioHistoryItem {
  id: string;
  audioUrl: string;
  text: string;
  voice: string;
  createdAt: string;
}

function configValue(config: UserConfig) {
  return `${config.source}:${config.id}`;
}

function configPayload(config: UserConfig | undefined) {
  if (!config) return {};
  return config.source === "official"
    ? { officialConfigId: config.id }
    : { configId: config.id };
}

function isAudioConfig(config: UserConfig) {
  return (
    config.purpose === "audio" &&
    config.provider === "qwen" &&
    config.isEnabled &&
    Boolean(config.modelSeries.trim())
  );
}

function readHistory(): AudioHistoryItem[] {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(window.localStorage.getItem(historyStorageKey) || "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

interface AudioGenerationPanelProps {
  configs: UserConfig[];
  officialConfigs: UserConfig[];
}

export function AudioGenerationPanel({
  configs,
  officialConfigs,
}: AudioGenerationPanelProps) {
  const { t, formatDateTime } = useI18n();
  const queryClient = useQueryClient();

  const [selectedConfigId, setSelectedConfigId] = useState("");
  const [source, setSource] = useState<VoiceSource>("custom");
  const [builtinVoice, setBuiltinVoice] = useState("");
  const [customVoiceId, setCustomVoiceId] = useState("");
  const [text, setText] = useState("");
  const [audioUrl, setAudioUrl] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [isDownloading, setIsDownloading] = useState(false);
  const [history, setHistory] = useState<AudioHistoryItem[]>(readHistory);

  // 音色创作弹窗状态
  const [designOpen, setDesignOpen] = useState(false);
  const [designName, setDesignName] = useState("");
  const [designPrompt, setDesignPrompt] = useState("");
  const [designText, setDesignText] = useState("");
  const [draftVoice, setDraftVoice] = useState<UserVoice | null>(null);

  const audioConfigs = useMemo(
    () => [...officialConfigs.filter(isAudioConfig), ...configs.filter(isAudioConfig)],
    [configs, officialConfigs]
  );

  const defaultConfigId = useMemo(() => {
    const config = audioConfigs.find((item) => item.isActive) ?? audioConfigs[0];
    return config ? configValue(config) : "";
  }, [audioConfigs]);

  const effectiveConfigId = audioConfigs.some((item) => configValue(item) === selectedConfigId)
    ? selectedConfigId
    : defaultConfigId;

  const selectedConfig = audioConfigs.find((item) => configValue(item) === effectiveConfigId);

  // 查询用户已保存的音色列表
  const voicesQuery = useQuery({
    queryKey: queryKeys.userVoices,
    queryFn: listUserVoicesAction,
  });

  const userVoices = voicesQuery.data?.voices ?? [];
  const effectiveCustomVoiceId = userVoices.some((item) => item.id === customVoiceId)
    ? customVoiceId
    : userVoices[0]?.id ?? "";
  const selectedCustomVoice = userVoices.find((v) => v.id === effectiveCustomVoiceId);
  const voice = source === "builtin" ? builtinVoice : effectiveCustomVoiceId;
  const resolvedAudioUrl = artifactBffUrl(audioUrl);

  // 合成音频 Mutation
  const generateMutation = useMutation({
    mutationFn: generateAudioAction,
    onSuccess: (response, variables) => {
      const nextItem: AudioHistoryItem = {
        id: `${Date.now()}`,
        audioUrl: response.audio.url,
        text: variables.text,
        voice: variables.voice,
        createdAt: new Date().toISOString(),
      };
      const nextList = [nextItem, ...history].slice(0, 20);
      setAudioUrl(response.audio.url);
      setHistory(nextList);
      window.localStorage.setItem(historyStorageKey, JSON.stringify(nextList));
      setErrorMessage(null);
    },
    onError: (error) =>
      setErrorMessage(resolveRequestError(error, t("audio.generateFailed"))),
  });

  // 提示词/朗读文本优化 Mutation
  const optimizeMutation = useMutation({
    mutationFn: () =>
      optimizePromptAction({
        kind: "audio",
        prompt: text.trim(),
        context: { voice },
      }),
    onSuccess: (response) => {
      setText(response.prompt);
      setErrorMessage(null);
    },
    onError: (error) =>
      setErrorMessage(resolveRequestError(error, t("audio.optimizeTextFailed"))),
  });

  // 创作音色（设计试听） Mutation
  const designMutation = useMutation({
    mutationFn: () =>
      designVoiceAction({
        name: designName.trim(),
        voicePrompt: designPrompt.trim(),
        previewText: designText.trim(),
        ...configPayload(selectedConfig),
      }),
    onSuccess: (response) => {
      setDraftVoice(response.voice);
      setErrorMessage(null);
    },
    onError: (error) =>
      setErrorMessage(resolveRequestError(error, t("audio.designFailed"))),
  });

  // 保存音色 Mutation
  const saveMutation = useMutation({
    mutationFn: () => saveVoiceAction(draftVoice!.id),
    onSuccess: (response) => {
      queryClient.setQueryData(
        queryKeys.userVoices,
        (current: { voices: UserVoice[] } | undefined) => ({
          voices: [response.voice, ...(current?.voices ?? [])],
        })
      );
      setSource("custom");
      setCustomVoiceId(response.voice.id);
      setDraftVoice(null);
      setDesignOpen(false);
      setDesignName("");
      setDesignPrompt("");
      setDesignText("");
    },
  });

  // 计时器
  useEffect(() => {
    if (!generateMutation.isPending) return;
    const started = Date.now();
    const timer = window.setInterval(
      () => setElapsedSeconds(Math.floor((Date.now() - started) / 1000)),
      1000
    );
    return () => window.clearInterval(timer);
  }, [generateMutation.isPending]);

  const handleGenerate = () => {
    const content = text.trim();
    if (!content || !voice || !selectedConfig || generateMutation.isPending) return;
    setElapsedSeconds(0);
    const payload: GenerateAudioInput = {
      text: content,
      voice,
      ...configPayload(selectedConfig),
    };
    generateMutation.mutate(payload);
  };

  const handleDownload = async () => {
    if (!audioUrl || isDownloading) return;
    setIsDownloading(true);
    setErrorMessage(null);
    try {
      const response = await fetch(resolvedAudioUrl);
      if (!response.ok) throw new Error("Download failed");
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = `sceneflow-voice-${Date.now()}.wav`;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
    } catch {
      setErrorMessage(t("audio.downloadFailed"));
    } finally {
      setIsDownloading(false);
    }
  };

  const generatingLabel = t("audio.generatingWithSeconds", { seconds: elapsedSeconds });

  return (
    <div className="grid min-h-0 flex-1 bg-background lg:grid-cols-[380px_minmax(0,1fr)]">
      {/* 左侧控制栏 */}
      <aside className="flex min-h-0 flex-col border-b border-border/70 bg-card/40 p-4 backdrop-blur-xl lg:border-r lg:border-b-0 lg:p-5">
        {/* 顶部标题栏 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <AudioLines className="size-4" />
            </div>
            <h2 className="text-sm font-bold tracking-tight text-foreground">
              {t("home.audioGeneration")}
            </h2>
          </div>
          <Badge variant="secondary" className="text-[10px] font-semibold tracking-wide">
            QWEN AUDIO
          </Badge>
        </div>

        {/* 滚动配置区 */}
        <div className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto px-1 chat-message-list-scrollbar">
          {/* 模型选择 */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-foreground/90">
              {t("audio.model")}
            </label>
            <Select
              value={effectiveConfigId}
              onValueChange={(val) => setSelectedConfigId(val ?? "")}
            >
              <SelectTrigger className="h-9 w-full text-xs">
                <SelectValue placeholder={t("audio.selectModel")}>
                  {selectedConfig ? configName(selectedConfig, t) : undefined}
                </SelectValue>
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                {audioConfigs.map((config) => (
                  <SelectItem
                    key={configValue(config)}
                    value={configValue(config)}
                    label={configName(config, t)}
                    className="text-xs"
                  >
                    {configName(config, t)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {audioConfigs.length === 0 ? (
              <p className="text-xs text-amber-500">{t("audio.noModel")}</p>
            ) : null}
          </div>

          {/* 音色来源与选择卡片 */}
          <div className="space-y-3 rounded-2xl border border-border/70 bg-card/30 p-3">
            <div className="flex items-center justify-between gap-2">
              <label className="text-xs font-semibold text-foreground/90">
                {t("audio.voiceSource")}
              </label>
              <Button
                type="button"
                variant="outline"
                size="xs"
                onClick={() => setDesignOpen(true)}
                className="h-7 gap-1 text-[11px] font-medium cursor-pointer shadow-2xs hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
              >
                <Plus className="size-3" />
                {t("audio.createVoice")}
              </Button>
            </div>

            {/* 分段切换 Pill Tabs */}
            <div className="grid grid-cols-2 gap-1 rounded-xl bg-muted/60 p-1">
              <button
                type="button"
                onClick={() => setSource("custom")}
                className={cn(
                  "flex h-7 items-center justify-center gap-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer",
                  source === "custom"
                    ? "bg-background text-foreground shadow-xs font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <User className="size-3 text-primary" />
                <span>{t("audio.myVoice")}</span>
                {userVoices.length > 0 ? (
                  <span className="ml-0.5 rounded-full bg-primary/15 px-1 text-[9px] text-primary">
                    {userVoices.length}
                  </span>
                ) : null}
              </button>
              <button
                type="button"
                onClick={() => setSource("builtin")}
                className={cn(
                  "flex h-7 items-center justify-center gap-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer",
                  source === "builtin"
                    ? "bg-background text-foreground shadow-xs font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Sparkles className="size-3 text-primary" />
                <span>{t("audio.officialVoice")}</span>
              </button>
            </div>

            {/* 音色配置：我的音色采用带有名称显示的下拉框，官方音色采用直接输入+快捷标签 */}
            {source === "custom" ? (
              <div className="space-y-1.5">
                <label className="text-[11px] font-medium text-muted-foreground">
                  {t("audio.myVoice")}
                </label>
                <Select value={effectiveCustomVoiceId} onValueChange={(val) => setCustomVoiceId(val ?? "")}>
                  <SelectTrigger className="h-9 w-full text-xs">
                    <SelectValue placeholder={t("audio.selectMyVoice")}>
                      {selectedCustomVoice ? (selectedCustomVoice.name || selectedCustomVoice.voiceId) : undefined}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent alignItemWithTrigger={false} className="max-h-60">
                    {userVoices.map((item) => (
                      <SelectItem
                        key={item.id}
                        value={item.id}
                        label={item.name || item.voiceId}
                        className="text-xs"
                      >
                        <div className="flex items-center justify-between gap-3 w-full">
                          <span className="font-semibold text-foreground">
                            {item.name || item.voiceId}
                          </span>
                          {item.voicePrompt ? (
                            <span className="truncate text-[11px] text-muted-foreground max-w-[150px]">
                              {item.voicePrompt}
                            </span>
                          ) : null}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {userVoices.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    {t("audio.noCustomVoice")}
                  </p>
                ) : null}
              </div>
            ) : (
              <div className="space-y-2">
                <div className="space-y-1.5">
                  <label className="text-[11px] font-medium text-muted-foreground">
                    {t("audio.officialVoiceName")}
                  </label>
                  <Input
                    value={builtinVoice}
                    onChange={(event) => setBuiltinVoice(event.target.value)}
                    placeholder={t("audio.voicePlaceholder") || "例如 Cherry、Dylan、Ethan"}
                    className="h-9 text-xs"
                  />
                </div>
              </div>
            )}
          </div>

          {/* 朗读文本输入区 */}
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <label className="text-xs font-semibold text-foreground/90">
                {t("audio.text")}
              </label>
              <Button
                type="button"
                variant="outline"
                size="xs"
                disabled={!text.trim() || optimizeMutation.isPending}
                onClick={() => optimizeMutation.mutate()}
                className="h-7 gap-1 text-[11px] cursor-pointer"
              >
                {optimizeMutation.isPending ? (
                  <Loader2 className="size-3 animate-spin text-primary" />
                ) : (
                  <Sparkles className="size-3 text-primary" />
                )}
                {optimizeMutation.isPending
                  ? t("audio.optimizingText")
                  : t("audio.optimizeText")}
              </Button>
            </div>
            <Textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder={t("audio.textPlaceholder")}
              className="min-h-32 resize-none rounded-xl text-xs"
            />
          </div>
        </div>

        {/* 历史生成记录 */}
        <div className="mt-3 border-t border-border/70 pt-3">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground/90">
              <History className="size-3.5 text-muted-foreground" />
              <span>{t("audio.history")}</span>
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
                  onClick={() => {
                    setAudioUrl(item.audioUrl);
                    setText(item.text);
                  }}
                  className="flex w-full items-center gap-2 rounded-xl border border-border/60 bg-card/60 p-2 text-left transition-all hover:border-primary/40 hover:bg-card cursor-pointer"
                >
                  <Music className="size-4 shrink-0 text-primary" />
                  <span className="min-w-0 flex-1 truncate text-xs font-medium text-foreground">
                    {item.text}
                  </span>
                  <span className="text-[10px] text-muted-foreground shrink-0">
                    {formatDateTime(item.createdAt)}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="py-2 text-center text-[11px] text-muted-foreground">
              {t("audio.historyEmpty")}
            </p>
          )}
        </div>

        {/* 立即合成主按钮 */}
        <div className="mt-3 border-t border-border/70 pt-3">
          <Button
            className="h-10 w-full gap-2 rounded-xl font-bold shadow-md cursor-pointer transition-all active:scale-[0.99]"
            onClick={handleGenerate}
            disabled={!text.trim() || !voice || !selectedConfig || generateMutation.isPending}
          >
            <Sparkles className="size-4" />
            {generateMutation.isPending ? generatingLabel : t("audio.generateNow")}
          </Button>
        </div>
      </aside>

      {/* 右侧：音频波形播放视口 */}
      <section className="flex min-h-0 min-w-0 flex-col p-4 md:p-6">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-bold tracking-tight text-foreground">
              {t("audio.preview")}
            </h2>
            {audioUrl ? (
              <Badge variant="default" className="text-[10px]">
                Audio Ready
              </Badge>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="h-8 gap-1.5 text-xs cursor-pointer"
              onClick={handleGenerate}
              disabled={!audioUrl || generateMutation.isPending}
            >
              <RotateCcw className="size-3.5" />
              {t("audio.regenerate")}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              className="h-8 gap-1.5 text-xs cursor-pointer font-semibold shadow-xs"
              onClick={handleDownload}
              disabled={!audioUrl || isDownloading}
            >
              <Download className="size-3.5" />
              {t("audio.download")}
            </Button>
          </div>
        </div>

        {/* 音频试听视口 */}
        <div className="relative mt-4 flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-3xl border border-border/80 bg-card/20 p-6 shadow-inner backdrop-blur-md dark:bg-black/20">
          <div className="pointer-events-none absolute inset-0 bg-grid-dots opacity-20" />

          {generateMutation.isPending ? (
            <div className="relative z-10 text-center space-y-4">
              <div className="relative mx-auto flex size-16 items-center justify-center rounded-2xl bg-primary/10 text-primary shadow-xs">
                <AudioLines className="size-8 animate-pulse" />
                <span className="absolute inset-0 size-16 animate-ping rounded-2xl bg-primary/20 opacity-40" />
              </div>
              <div>
                <p className="text-sm font-bold text-foreground">{generatingLabel}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  正在进行高保真语音合成与声波渲染...
                </p>
              </div>
              {/* 跳动的音频波形装饰 */}
              <div className="flex items-center justify-center gap-1">
                {[40, 75, 55, 90, 60, 85, 45, 95, 65, 50].map((h, i) => (
                  <span
                    key={i}
                    className="w-1 rounded-full bg-primary/60 animate-pulse"
                    style={{
                      height: `${h * 0.3}px`,
                      animationDelay: `${i * 120}ms`,
                      animationDuration: "900ms",
                    }}
                  />
                ))}
              </div>
            </div>
          ) : audioUrl ? (
            <div className="relative z-10 flex w-full max-w-md flex-col items-center gap-5 rounded-2xl border border-border/80 bg-card/80 p-6 shadow-xl backdrop-blur-xl animate-in fade-in-0 duration-300">
              <div className="flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary shadow-xs ring-1 ring-primary/20">
                <Volume2 className="size-7" />
              </div>
              <div className="w-full text-center space-y-1.5">
                <div className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-0.5 text-[11px] font-semibold text-primary">
                  <Sparkles className="size-3" />
                  <span>Voice: {voice}</span>
                </div>
                <div className="rounded-xl border border-border/60 bg-muted/30 p-3 text-left">
                  <p className="line-clamp-3 text-xs leading-relaxed font-medium text-foreground">
                    &ldquo;{text}&rdquo;
                  </p>
                </div>
              </div>
              <audio src={resolvedAudioUrl} controls className="w-full" autoPlay />
            </div>
          ) : (
            <div className="relative z-10 text-center space-y-2">
              <div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-muted/60 text-muted-foreground shadow-xs">
                <Mic className="size-7" />
              </div>
              <p className="text-sm font-semibold text-foreground">{t("audio.emptyPreview")}</p>
              <p className="max-w-xs text-xs text-muted-foreground">
                在左侧输入文本并选择音色，即可合成高质量自然语音
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

      {/* 创作音色 Dialog */}
      <Dialog
        open={designOpen}
        onOpenChange={(open) => {
          setDesignOpen(open);
          if (!open) setDraftVoice(null);
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <div className="flex items-center gap-2">
              <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Wand2 className="size-4" />
              </div>
              <div>
                <DialogTitle>{t("audio.createVoice")}</DialogTitle>
                <DialogDescription className="text-xs mt-0.5">
                  {t("audio.createVoiceHint")}
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>

          {draftVoice ? (
            <div className="space-y-3 py-2">
              <div className="rounded-xl border border-border/70 bg-card/60 p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-foreground">
                    {draftVoice.name}
                  </span>
                  <Badge variant="secondary" className="text-[10px]">
                    Draft Ready
                  </Badge>
                </div>
                {draftVoice.previewAudioUrl ? (
                  <audio
                    src={artifactBffUrl(draftVoice.previewAudioUrl)}
                    controls
                    className="w-full"
                    autoPlay
                  />
                ) : null}
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {t("audio.voiceDraftHint")}
              </p>
            </div>
          ) : (
            <div className="space-y-3 py-2">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-foreground/90">
                  {t("voice.name")}
                </label>
                <Input
                  value={designName}
                  onChange={(event) => setDesignName(event.target.value)}
                  placeholder={t("audio.voiceNamePlaceholder")}
                  className="h-9 text-xs"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-foreground/90">
                  {t("voice.note")}
                </label>
                <Textarea
                  value={designPrompt}
                  onChange={(event) => setDesignPrompt(event.target.value)}
                  placeholder={t("audio.voicePromptPlaceholder")}
                  className="min-h-20 resize-none text-xs rounded-lg"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-foreground/90">
                  {t("voice.sampleText")}
                </label>
                <Textarea
                  value={designText}
                  onChange={(event) => setDesignText(event.target.value)}
                  placeholder={t("audio.voicePreviewTextPlaceholder")}
                  className="min-h-16 resize-none text-xs rounded-lg"
                />
              </div>
            </div>
          )}

          <DialogFooter className="gap-2 sm:gap-2.5">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDesignOpen(false)}
              className="h-9 text-xs"
            >
              {t("common.cancel")}
            </Button>
            {draftVoice ? (
              <Button
                size="sm"
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending}
                className="h-9 gap-1 text-xs"
              >
                {saveMutation.isPending ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Check className="size-3.5" />
                )}
                {saveMutation.isPending ? t("common.saving") : t("common.save")}
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={() => designMutation.mutate()}
                disabled={
                  !designName.trim() ||
                  !designPrompt.trim() ||
                  !designText.trim() ||
                  designMutation.isPending
                }
                className="h-9 gap-1 text-xs"
              >
                {designMutation.isPending ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Sparkles className="size-3.5" />
                )}
                {designMutation.isPending ? t("common.saving") : t("audio.createVoice")}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
