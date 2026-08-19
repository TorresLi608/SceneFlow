"use client";

import { useMutation } from "@tanstack/react-query";
import {
  AudioLines,
  Download,
  History,
  Loader2,
  Mic,
  Music,
  RotateCcw,
  Sparkles,
  Volume2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { generateAudioAction } from "@/actions/audio-generation-actions";
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
import type { AudioFormat, GenerateAudioInput } from "@/types/audio-generation";

const historyStorageKey = "sceneflow-audio-generation-history-v1";

interface AudioHistoryItem {
  id: string;
  audioUrl: string;
  text: string;
  voice: string;
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

function isAudioConfig(config: UserConfig) {
  return (
    config.purpose === "audio" &&
    config.provider === "qwen" &&
    config.isEnabled &&
    Boolean(config.modelSeries.trim())
  );
}

function readHistory() {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(historyStorageKey) || "[]");
    return Array.isArray(parsed) ? (parsed as AudioHistoryItem[]) : [];
  } catch {
    return [];
  }
}

function saveHistory(items: AudioHistoryItem[]) {
  window.localStorage.setItem(historyStorageKey, JSON.stringify(items.slice(0, 20)));
}

function configuredVoice(config: UserConfig | undefined) {
  return config?.modelSeries.split(":").slice(1).join(":").trim() || "";
}

export function AudioGenerationPanel({
  configs,
  officialConfigs,
}: {
  configs: UserConfig[];
  officialConfigs: UserConfig[];
}) {
  const { t, formatDateTime } = useI18n();
  const [selectedConfigId, setSelectedConfigId] = useState("");
  const [voiceOverride, setVoiceOverride] = useState<string | null>(null);
  const [format, setFormat] = useState<AudioFormat>("mp3_24000");
  const [volume, setVolume] = useState(50);
  const [speechRate, setSpeechRate] = useState(1);
  const [pitchRate, setPitchRate] = useState(1);
  const [seed, setSeed] = useState(0);
  const [language, setLanguage] = useState("auto");
  const [instruction, setInstruction] = useState("");
  const [text, setText] = useState("");
  const [audioUrl, setAudioUrl] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [isDownloading, setIsDownloading] = useState(false);
  const [history, setHistory] = useState<AudioHistoryItem[]>(readHistory);

  const audioConfigs = useMemo(
    () => [...officialConfigs.filter(isAudioConfig), ...configs.filter(isAudioConfig)],
    [configs, officialConfigs]
  );
  const defaultConfigId = useMemo(() => {
    const config = audioConfigs.find((item) => item.isActive) ?? audioConfigs[0];
    return config ? configSelectValue(config) : "";
  }, [audioConfigs]);
  const effectiveConfigId = audioConfigs.some(
    (config) => configSelectValue(config) === selectedConfigId
  )
    ? selectedConfigId
    : defaultConfigId;
  const selectedConfig = audioConfigs.find(
    (config) => configSelectValue(config) === effectiveConfigId
  );
  const voice = voiceOverride ?? configuredVoice(selectedConfig);
  const resolvedAudioUrl = artifactBffUrl(audioUrl);

  const generateMutation = useMutation({
    mutationFn: generateAudioAction,
    onSuccess: (response, variables) => {
      const item = {
        id: `${Date.now()}`,
        audioUrl: response.audio.url,
        text: variables.text,
        voice: variables.voice,
        createdAt: new Date().toISOString(),
      };
      setAudioUrl(response.audio.url);
      setHistory((current) => {
        const next = [item, ...current].slice(0, 20);
        saveHistory(next);
        return next;
      });
      setErrorMessage(null);
    },
    onError: (error) =>
      setErrorMessage(resolveRequestError(error, t("audio.generateFailed"))),
  });

  const optimizeMutation = useMutation({
    mutationFn: () =>
      optimizePromptAction({
        kind: "audio",
        prompt: text.trim(),
        context: {
          voice: voice.trim() || undefined,
          speechRate,
          pitchRate,
          instruction: instruction.trim() || undefined,
          language,
        },
      }),
    onSuccess: (response) => {
      setText(response.prompt);
      setErrorMessage(null);
    },
    onError: (error) =>
      setErrorMessage(resolveRequestError(error, t("audio.optimizeTextFailed"))),
  });

  useEffect(() => {
    if (!generateMutation.isPending) return;
    const startedAt = Date.now();
    const timer = window.setInterval(
      () => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000)),
      1000
    );
    return () => window.clearInterval(timer);
  }, [generateMutation.isPending]);

  const generate = () => {
    const content = text.trim();
    const selectedVoice = voice.trim();
    if (!content || !selectedVoice || !selectedConfig || generateMutation.isPending) return;
    setElapsedSeconds(0);
    const payload: GenerateAudioInput = {
      text: content,
      voice: selectedVoice,
      format,
      volume,
      speechRate,
      pitchRate,
      seed,
      instruction: instruction.trim() || undefined,
      ...selectedConfigPayload(selectedConfig),
    };
    generateMutation.mutate(payload);
  };

  const downloadAudio = async () => {
    if (!audioUrl || isDownloading) return;
    setIsDownloading(true);
    setErrorMessage(null);
    try {
      const response = await fetch(resolvedAudioUrl);
      if (!response.ok) throw new Error(`Download failed: ${response.status}`);
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = `sceneflow-audio-${Date.now()}.mp3`;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    } catch {
      setErrorMessage(t("audio.downloadFailed"));
    } finally {
      setIsDownloading(false);
    }
  };

  const generatingLabel = t("audio.generatingAudioWithSeconds", { seconds: elapsedSeconds });

  return (
    <div className="grid min-h-0 flex-1 bg-background lg:grid-cols-[380px_minmax(0,1fr)]">
      {/* 左侧控制台 */}
      <aside className="flex min-h-0 flex-col border-b border-border/70 bg-card/40 p-4 backdrop-blur-xl lg:border-r lg:border-b-0 lg:p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <AudioLines className="size-4" />
            </div>
            <h2 className="text-sm font-bold tracking-tight text-foreground">
              {t("home.audioGeneration")}
            </h2>
          </div>
          <Badge variant="secondary" className="text-[10px]">
            AI Studio
          </Badge>
        </div>

        <div className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto px-1 chat-message-list-scrollbar">
          {/* 模型与音色选择 */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-foreground/90">{t("audio.model")}</label>
            <Select
              value={effectiveConfigId}
              onValueChange={(val) => {
                setSelectedConfigId(val ?? "");
                setVoiceOverride(null);
              }}
            >
              <SelectTrigger className="h-9 text-xs">
                <SelectValue placeholder={t("audio.selectModel")}>
                  {selectedConfig ? configName(selectedConfig, t) : undefined}
                </SelectValue>
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                {audioConfigs.map((config) => (
                  <SelectItem
                    key={configSelectValue(config)}
                    value={configSelectValue(config)}
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

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-foreground/90">{t("audio.voice")}</label>
            <Input
              value={voice}
              onChange={(event) => setVoiceOverride(event.target.value)}
              placeholder="zh_female_cancan / custom_voice"
              className="h-9 text-xs"
            />
          </div>

          {/* 语速、音调、音量 */}
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-muted-foreground">
                {t("audio.speechRate")}
              </label>
              <Input
                type="number"
                step={0.1}
                min={0.5}
                max={2.0}
                value={speechRate}
                onChange={(event) => setSpeechRate(Number(event.target.value))}
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-muted-foreground">
                {t("audio.pitchRate")}
              </label>
              <Input
                type="number"
                step={0.1}
                min={0.5}
                max={2.0}
                value={pitchRate}
                onChange={(event) => setPitchRate(Number(event.target.value))}
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-muted-foreground">
                {t("audio.volume")}
              </label>
              <Input
                type="number"
                min={0}
                max={100}
                value={volume}
                onChange={(event) => setVolume(Number(event.target.value))}
                className="h-8 text-xs"
              />
            </div>
          </div>

          {/* 朗读文本 */}
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <label className="text-xs font-semibold text-foreground/90">{t("audio.text")}</label>
              <Button
                type="button"
                variant="outline"
                size="xs"
                disabled={!text.trim() || optimizeMutation.isPending}
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
            <Textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder={t("audio.textPlaceholder")}
              className="min-h-28 rounded-xl text-xs resize-none"
            />
          </div>
        </div>

        {/* 历史生成 */}
        <div className="mt-3 border-t border-border/70 pt-3">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-semibold">
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
                  onClick={() => setAudioUrl(item.audioUrl)}
                  className="flex w-full items-center gap-2 rounded-xl border border-border/60 bg-card/60 p-2 text-left transition-all hover:border-primary/40 hover:bg-card cursor-pointer"
                >
                  <Music className="size-4 shrink-0 text-primary" />
                  <span className="min-w-0 flex-1 truncate text-xs font-medium text-foreground">
                    {item.text}
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    {formatDateTime(item.createdAt)}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="text-center py-2 text-[11px] text-muted-foreground">
              {t("audio.historyEmpty")}
            </p>
          )}
        </div>

        {/* 立即合成按钮 */}
        <div className="mt-3 border-t border-border/70 pt-3">
          <Button
            className="h-10 w-full gap-2 rounded-xl font-bold shadow-md cursor-pointer transition-all active:scale-[0.99]"
            onClick={generate}
            disabled={!text.trim() || !voice.trim() || !selectedConfig || generateMutation.isPending}
          >
            <Sparkles className="size-4" />
            {generateMutation.isPending ? generatingLabel : t("audio.generateNow")}
          </Button>
        </div>
      </aside>

      {/* 右侧：音频波形播放区 */}
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
              onClick={generate}
              disabled={!audioUrl || generateMutation.isPending}
            >
              <RotateCcw className="size-3.5" />
              {t("audio.regenerate")}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              className="h-8 gap-1.5 text-xs cursor-pointer font-semibold shadow-xs"
              onClick={downloadAudio}
              disabled={!audioUrl || isDownloading}
            >
              <Download className="size-3.5" />
              {t("audio.download")}
            </Button>
          </div>
        </div>

        {/* 音频试听视口 */}
        <div className="mt-4 flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-3xl border border-border/80 bg-card/20 p-6 shadow-inner backdrop-blur-md relative dark:bg-black/20">
          <div className="pointer-events-none absolute inset-0 bg-grid-dots opacity-20" />

          {generateMutation.isPending ? (
            <div className="relative z-10 text-center">
              <div className="relative mx-auto mb-4 flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <AudioLines className="size-7 animate-pulse" />
                <span className="absolute inset-0 size-14 animate-ping rounded-2xl bg-primary/20 opacity-40" />
              </div>
              <p className="text-sm font-semibold text-foreground">{generatingLabel}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                正在进行声音波形克隆与情感语音合成...
              </p>
            </div>
          ) : audioUrl ? (
            <div className="relative z-10 flex w-full max-w-md flex-col items-center gap-4 rounded-2xl border border-border/80 bg-card/80 p-6 shadow-xl backdrop-blur-xl animate-in fade-in-0 duration-300">
              <div className="flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary shadow-xs">
                <Volume2 className="size-7" />
              </div>
              <div className="w-full text-center">
                <p className="truncate text-sm font-bold text-foreground">{text}</p>
                <p className="mt-1 text-xs text-muted-foreground">Voice: {voice}</p>
              </div>
              <audio src={resolvedAudioUrl} controls className="w-full" autoPlay />
            </div>
          ) : (
            <div className="relative z-10 text-center">
              <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-2xl bg-muted/60 text-muted-foreground">
                <Mic className="size-6" />
              </div>
              <p className="text-sm font-semibold text-foreground">{t("audio.emptyPreview")}</p>
              <p className="mt-1 text-xs text-muted-foreground">
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
    </div>
  );
}
