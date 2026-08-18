"use client";

import { useMutation } from "@tanstack/react-query";
import { AudioLines, Download, Loader2, RotateCcw, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { generateAudioAction } from "@/actions/audio-generation-actions";
import { optimizePromptAction } from "@/actions/prompt-actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
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
  return config.source === "official" ? { officialConfigId: config.id } : { configId: config.id };
}

function isAudioConfig(config: UserConfig) {
  return config.purpose === "audio" && config.provider === "qwen" && config.isEnabled && Boolean(config.modelSeries.trim());
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

export function AudioGenerationPanel({ configs, officialConfigs }: { configs: UserConfig[]; officialConfigs: UserConfig[] }) {
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

  const audioConfigs = useMemo(() => [...officialConfigs.filter(isAudioConfig), ...configs.filter(isAudioConfig)], [configs, officialConfigs]);
  const defaultConfigId = useMemo(() => {
    const config = audioConfigs.find((item) => item.isActive) ?? audioConfigs[0];
    return config ? configSelectValue(config) : "";
  }, [audioConfigs]);
  const effectiveConfigId = audioConfigs.some((config) => configSelectValue(config) === selectedConfigId) ? selectedConfigId : defaultConfigId;
  const selectedConfig = audioConfigs.find((config) => configSelectValue(config) === effectiveConfigId);
  const voice = voiceOverride ?? configuredVoice(selectedConfig);
  const resolvedAudioUrl = artifactBffUrl(audioUrl);

  const generateMutation = useMutation({
    mutationFn: generateAudioAction,
    onSuccess: (response, variables) => {
      const item = { id: `${Date.now()}`, audioUrl: response.audio.url, text: variables.text, voice: variables.voice, createdAt: new Date().toISOString() };
      setAudioUrl(response.audio.url);
      setHistory((current) => {
        const next = [item, ...current].slice(0, 20);
        saveHistory(next);
        return next;
      });
      setErrorMessage(null);
    },
    onError: (error) => setErrorMessage(resolveRequestError(error, t("audio.generateFailed"))),
  });

  const optimizeMutation = useMutation({
    mutationFn: () => optimizePromptAction({
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
    onError: (error) => setErrorMessage(resolveRequestError(error, t("audio.optimizeTextFailed"))),
  });

  useEffect(() => {
    if (!generateMutation.isPending) return;
    const startedAt = Date.now();
    const timer = window.setInterval(() => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000)), 1000);
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
      languageHints: language === "auto" ? [] : language === "both" ? ["zh", "en"] : [language as "zh" | "en"],
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
      link.download = `sceneflow-audio-${Date.now()}.${format.startsWith("wav") ? "wav" : "mp3"}`;
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

  const generatingLabel = t("audio.generatingWithSeconds", { seconds: elapsedSeconds });

  return (
    <div className="grid min-h-0 flex-1 bg-background md:grid-cols-[360px_minmax(0,1fr)]">
      <aside className="flex min-h-0 flex-col border-b border-border/60 bg-muted/20 p-4 md:border-r md:border-b-0">
        <div className="flex items-center gap-2"><AudioLines className="size-4" /><h2 className="text-sm font-semibold">{t("home.audioGeneration")}</h2></div>
        <div className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
          <div className="space-y-1.5"><label className="text-sm font-medium">{t("audio.model")}</label><Select value={effectiveConfigId} onValueChange={(value) => { setSelectedConfigId(value ?? ""); setVoiceOverride(null); }}><SelectTrigger><SelectValue placeholder={t("audio.selectModel")}>{selectedConfig ? configName(selectedConfig, t) : undefined}</SelectValue></SelectTrigger><SelectContent alignItemWithTrigger={false}>{audioConfigs.map((config) => <SelectItem key={configSelectValue(config)} value={configSelectValue(config)}>{configName(config, t)}</SelectItem>)}</SelectContent></Select>{audioConfigs.length === 0 ? <p className="text-xs text-amber-600">{t("audio.noModel")}</p> : null}</div>
          <div className="space-y-1.5"><label className="text-sm font-medium">{t("audio.voice")}</label><Input value={voice} onChange={(event) => setVoiceOverride(event.target.value)} placeholder={t("audio.voicePlaceholder")} /></div>
          <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-1 lg:grid-cols-2">
            <NumberField label={t("audio.volume")} value={volume} min={0} max={100} step={1} onChange={setVolume} />
            <NumberField label={t("audio.speechRate")} value={speechRate} min={0.5} max={2} step={0.1} onChange={setSpeechRate} />
            <NumberField label={t("audio.pitchRate")} value={pitchRate} min={0.5} max={2} step={0.1} onChange={setPitchRate} />
            <NumberField label={t("audio.seed")} value={seed} min={0} max={65535} step={1} onChange={setSeed} />
          </div>
          <div className="space-y-1.5"><label className="text-sm font-medium">{t("audio.format")}</label><Select value={format} onValueChange={(value) => setFormat(value as AudioFormat)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent alignItemWithTrigger={false}><SelectItem value="mp3_24000">MP3 · 24 kHz</SelectItem><SelectItem value="wav_24000">WAV · 24 kHz</SelectItem></SelectContent></Select></div>
          <div className="space-y-1.5"><label className="text-sm font-medium">{t("audio.language")}</label><Select value={language} onValueChange={(value) => setLanguage(value ?? "auto")}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent alignItemWithTrigger={false}><SelectItem value="auto">{t("audio.languageAuto")}</SelectItem><SelectItem value="zh">{t("audio.languageZh")}</SelectItem><SelectItem value="en">{t("audio.languageEn")}</SelectItem><SelectItem value="both">{t("audio.languageBoth")}</SelectItem></SelectContent></Select></div>
          <div className="space-y-1.5"><label className="text-sm font-medium">{t("audio.instruction")}</label><Input value={instruction} maxLength={128} onChange={(event) => setInstruction(event.target.value)} placeholder={t("audio.instructionPlaceholder")} /></div>
          <div className="space-y-1.5"><div className="flex items-center justify-between gap-2"><label className="text-sm font-medium">{t("audio.text")}</label><Button type="button" variant="ghost" size="sm" disabled={!text.trim() || optimizeMutation.isPending} onClick={() => optimizeMutation.mutate()}>{optimizeMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}{optimizeMutation.isPending ? t("audio.optimizingText") : t("audio.optimizeText")}</Button></div><Textarea value={text} onChange={(event) => setText(event.target.value)} placeholder={t("audio.textPlaceholder")} className="min-h-32 resize-none" /></div>
        </div>
        <div className="mt-4 border-t border-border/70 pt-4">
          <div className="mb-2 flex items-center justify-between gap-2"><h3 className="text-sm font-semibold">{t("audio.history")}</h3><span className="text-xs text-muted-foreground">{history.length}</span></div>
          {history.length ? <div className="max-h-44 space-y-2 overflow-y-auto pr-1">{history.map((item) => <button key={item.id} type="button" onClick={() => setAudioUrl(item.audioUrl)} className="flex w-full items-center gap-3 rounded-md border border-border/70 bg-background/60 p-2 text-left hover:bg-muted/60"><AudioLines className="size-4 shrink-0" /><span className="min-w-0 flex-1"><span className="block truncate text-xs font-medium">{item.voice} · {item.text}</span><span className="mt-1 block text-xs text-muted-foreground">{formatDateTime(item.createdAt)}</span></span></button>)}</div> : <p className="text-xs text-muted-foreground">{t("audio.historyEmpty")}</p>}
        </div>
        <div className="mt-4 border-t border-border/70 pt-4"><Button className="w-full" onClick={generate} disabled={!text.trim() || !voice.trim() || !selectedConfig || generateMutation.isPending}><Sparkles className="size-4" />{generateMutation.isPending ? generatingLabel : t("audio.generateNow")}</Button></div>
      </aside>
      <section className="flex min-h-0 min-w-0 flex-col p-4 md:p-6">
        <div className="flex items-center justify-between gap-2"><h2 className="text-sm font-semibold">{t("audio.preview")}</h2><div className="flex gap-2"><Button variant="secondary" size="sm" onClick={generate} disabled={!audioUrl || generateMutation.isPending}><RotateCcw className="size-4" />{t("audio.regenerate")}</Button><Button variant="secondary" size="sm" onClick={downloadAudio} disabled={!audioUrl || isDownloading}><Download className="size-4" />{t("audio.download")}</Button></div></div>
        <div className="mt-4 flex min-h-0 flex-1 flex-col items-center justify-center gap-5 rounded-md border border-dashed border-muted-foreground/50 bg-muted/10 p-6">
          {generateMutation.isPending ? <div className="text-center text-sm text-muted-foreground"><Sparkles className="mx-auto mb-3 size-5 animate-pulse" />{generatingLabel}</div> : audioUrl ? <audio key={resolvedAudioUrl} src={resolvedAudioUrl} controls className="w-full max-w-xl" /> : <div className="text-center text-sm text-muted-foreground"><AudioLines className="mx-auto mb-3 size-6" />{t("audio.emptyPreview")}</div>}
        </div>
        {errorMessage ? <p className="mt-3 text-sm text-amber-600">{errorMessage}</p> : null}
      </section>
    </div>
  );
}

function NumberField({ label, value, min, max, step, onChange }: { label: string; value: number; min: number; max: number; step: number; onChange: (value: number) => void }) {
  return <div className="space-y-1.5"><label className="text-sm font-medium">{label}</label><Input type="number" min={min} max={max} step={step} value={value} onChange={(event) => onChange(Math.min(max, Math.max(min, Number(event.target.value) || min)))} /></div>;
}
