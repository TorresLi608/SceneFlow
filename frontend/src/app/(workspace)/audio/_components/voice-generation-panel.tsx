"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AudioLines,
  Check,
  Copy,
  Download,
  Loader2,
  Maximize2,
  Save,
  Sparkles,
  Square,
  Trash2,
  Volume2,
  Wand2,
} from "lucide-react";
import { isCancel } from "axios";
import { useMemo, useRef, useState } from "react";

import { optimizePromptAction } from "@/actions/prompt-actions";
import {
  designVoiceAction,
  deleteVoiceAction,
  listUserVoicesAction,
  saveVoiceAction,
} from "@/actions/voice-generation-actions";
import { queryKeys } from "@/actions/query-keys";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { artifactBffUrl } from "@/lib/artifact-url";
import { configName } from "@/lib/config-format";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { UserConfig } from "@/types/auth";
import type { UserVoice } from "@/types/voice-generation";

function configValue(config: UserConfig) {
  return `${config.source}:${config.id}`;
}

function configPayload(config: UserConfig | undefined) {
  if (!config) return {};
  return config.source === "official"
    ? { officialConfigId: config.id }
    : { configId: config.id };
}

function isVoiceConfig(config: UserConfig) {
  return config.purpose === "audio" && config.provider === "qwen" && config.isEnabled && Boolean(config.modelSeries.trim());
}

export function VoiceGenerationPanel({
  configs,
  officialConfigs,
}: {
  configs: UserConfig[];
  officialConfigs: UserConfig[];
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [selectedConfigId, setSelectedConfigId] = useState("");
  const [selectedVoiceId, setSelectedVoiceId] = useState("");
  const [name, setName] = useState("");
  const [voicePrompt, setVoicePrompt] = useState("");
  const [promptLanguage, setPromptLanguage] = useState<"auto" | "zh" | "en">("auto");
  const [previewText, setPreviewText] = useState("");
  const [draftVoice, setDraftVoice] = useState<UserVoice | null>(null);
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyPrompt = (text: string) => {
    void navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const downloadAudio = (url: string, filename?: string) => {
    const link = document.createElement("a");
    link.href = url;
    link.download = filename || "voice_preview.wav";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
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

  const voiceConfigs = useMemo(
    () => [...officialConfigs.filter(isVoiceConfig), ...configs.filter(isVoiceConfig)],
    [configs, officialConfigs]
  );
  const defaultConfigId = useMemo(() => {
    const config = voiceConfigs.find((item) => item.isActive) ?? voiceConfigs[0];
    return config ? configValue(config) : "";
  }, [voiceConfigs]);
  const effectiveConfigId = voiceConfigs.some((item) => configValue(item) === selectedConfigId)
    ? selectedConfigId
    : defaultConfigId;
  const selectedConfig = voiceConfigs.find((item) => configValue(item) === effectiveConfigId);

  const voicesQuery = useQuery({
    queryKey: queryKeys.userVoices,
    queryFn: listUserVoicesAction,
  });
  const savedVoices = voicesQuery.data?.voices ?? [];
  const effectiveSavedVoiceId = savedVoices.some((item) => item.id === selectedVoiceId)
    ? selectedVoiceId
    : savedVoices[0]?.id ?? "";
  const savedPreview = savedVoices.find((item) => item.id === effectiveSavedVoiceId) ?? null;
  const previewVoice = draftVoice ?? savedPreview;

  const designMutation = useMutation({
    mutationFn: () =>
      designVoiceAction({
        name: name.trim(),
        voicePrompt: voicePrompt.trim(),
        previewText: previewText.trim(),
        ...configPayload(selectedConfig),
      }, requestController.current?.signal),
    onSuccess: ({ voice }) => {
      setDraftVoice(voice);
      setErrorMessage(null);
    },
    onError: (error) => {
      if (isCancel(error)) return;
      setErrorMessage(resolveRequestError(error, t("voice.designFailed")));
    },
    onSettled: () => { requestController.current = null; },
  });

  const optimizeMutation = useMutation({
    mutationFn: () =>
      optimizePromptAction(
        {
          kind: "voice",
          prompt: voicePrompt.trim(),
          context: { outputLanguage: promptLanguage },
        },
        optimizeController.current?.signal
      ),
    onSuccess: (response) => {
      setVoicePrompt(response.prompt);
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

  const saveMutation = useMutation({
    mutationFn: () => saveVoiceAction(draftVoice!.id),
    onSuccess: ({ voice }) => {
      queryClient.setQueryData(
        queryKeys.userVoices,
        (current: { voices: UserVoice[] } | undefined) => ({
          voices: [voice, ...(current?.voices ?? []).filter((item) => item.id !== voice.id)],
        })
      );
      setSelectedVoiceId(voice.id);
      setDraftVoice(null);
      setErrorMessage(null);
    },
    onError: (error) => setErrorMessage(resolveRequestError(error, t("voice.saveFailed"))),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteVoiceAction,
    onSuccess: (_, deletedId) => {
      queryClient.setQueryData(
        queryKeys.userVoices,
        (current: { voices: UserVoice[] } | undefined) => ({ voices: (current?.voices ?? []).filter((item) => item.id !== deletedId) })
      );
      if (selectedVoiceId === deletedId) setSelectedVoiceId("");
      setErrorMessage(null);
    },
    onError: (error) => setErrorMessage(resolveRequestError(error, t("voice.deleteFailed"))),
  });

  const canGenerate = Boolean(selectedConfig && name.trim() && voicePrompt.trim() && previewText.trim());

  const stopGeneration = () => {
    requestController.current?.abort();
    requestController.current = null;
    designMutation.reset();
  };

  const startGeneration = () => {
    requestController.current = new AbortController();
    designMutation.mutate();
  };

  return (
    <div className="grid min-h-0 flex-1 bg-background lg:grid-cols-[340px_minmax(0,1fr)]">
      <aside className="flex min-h-0 flex-col border-b border-border/70 bg-card/35 p-4 backdrop-blur-xl lg:border-r lg:border-b-0 lg:p-5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="flex size-8 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <AudioLines className="size-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold">{t("home.audioGeneration")}</h2>
              <p className="text-[11px] text-muted-foreground">{t("voice.workspaceHint")}</p>
            </div>
          </div>
          <Badge variant="secondary" className="text-[10px]">VOICE DESIGN</Badge>
        </div>

        <div className="mt-5 space-y-2">
          <label className="text-xs font-semibold" htmlFor="voice-model">{t("voice.designModel")}</label>
          <Select value={effectiveConfigId} onValueChange={(value) => setSelectedConfigId(value ?? "")}>
            <SelectTrigger id="voice-model" className="h-10 text-xs">
              <SelectValue placeholder={t("voice.selectModel")}>
                {selectedConfig ? configName(selectedConfig, t) : undefined}
              </SelectValue>
            </SelectTrigger>
            <SelectContent alignItemWithTrigger={false}>
              {voiceConfigs.map((config) => (
                <SelectItem key={configValue(config)} value={configValue(config)} label={configName(config, t)}>
                  {configName(config, t)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {voiceConfigs.length === 0 ? (
            <p className="text-xs text-amber-500">{t("voice.noModel")}</p>
          ) : null}
        </div>

        <div className="mt-5 flex min-h-0 flex-1 flex-col border-t border-border/70 pt-4">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold">{t("voice.saved")}</p>
            <Badge variant="outline" className="text-[10px]">{savedVoices.length}</Badge>
          </div>
          <div className="mt-2 min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1 chat-message-list-scrollbar">
            {savedVoices.map((voice) => (
              <div key={voice.id} className={cn("flex w-full items-center gap-1 rounded-xl px-1", !draftVoice && effectiveSavedVoiceId === voice.id ? "bg-primary/10" : "hover:bg-muted/60")}>
                <button
                  type="button"
                  onClick={() => { setSelectedVoiceId(voice.id); setDraftVoice(null); }}
                  className={cn("flex min-w-0 flex-1 items-center gap-3 rounded-xl px-2 py-2.5 text-left transition-colors", !draftVoice && effectiveSavedVoiceId === voice.id ? "text-foreground" : "text-muted-foreground hover:text-foreground")}
                >
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-background/80 text-primary shadow-xs">
                    <Volume2 className="size-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-semibold">{voice.name || voice.voiceId}</span>
                    <span className="block truncate text-[10px] opacity-70">{voice.targetModel}</span>
                  </span>
                  {!draftVoice && effectiveSavedVoiceId === voice.id ? <Check className="size-3.5 text-primary" /> : null}
                </button>
                <Button type="button" variant="ghost" size="icon-xs" onClick={() => deleteMutation.mutate(voice.id)} disabled={deleteMutation.isPending} aria-label={t("voice.delete")} className="shrink-0 text-muted-foreground hover:text-destructive">
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            ))}
            {!voicesQuery.isPending && savedVoices.length === 0 ? (
              <p className="py-8 text-center text-xs text-muted-foreground">{t("voice.savedEmpty")}</p>
            ) : null}
          </div>
        </div>
      </aside>

      <section className="flex min-h-0 min-w-0 flex-col overflow-y-auto p-4 md:p-7 chat-message-list-scrollbar">
        <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
          <header className="border-b border-border/70 pb-5">
            <div className="flex items-center gap-2 text-primary">
              <Wand2 className="size-4" />
              <span className="text-xs font-bold uppercase tracking-[0.18em]">{t("voice.eyebrow")}</span>
            </div>
            <h1 className="mt-2 text-2xl font-bold tracking-tight">{t("voice.create")}</h1>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t("voice.createHint")}</p>
          </header>

          <div className="grid gap-5 md:grid-cols-2">
            <div className="space-y-2 md:col-span-2">
              <label htmlFor="voice-name" className="text-xs font-semibold text-foreground/90">
                {t("voice.name")}
              </label>
              <Input
                id="voice-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={t("voice.namePlaceholder")}
                className="h-10 text-xs rounded-xl"
              />
            </div>
            <div className="space-y-2">
              <div className="flex h-7 items-center justify-between gap-2">
                <label htmlFor="voice-prompt" className="text-xs font-semibold text-foreground/90">
                  {t("voice.prompt")}
                </label>
                <div className="flex items-center gap-1.5">
                  <Select
                    value={promptLanguage}
                    onValueChange={(value) =>
                      setPromptLanguage((value ?? "auto") as "auto" | "zh" | "en")
                    }
                  >
                    <SelectTrigger className="h-7 min-w-20 text-[11px]">
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
                    disabled={!voicePrompt.trim() && !optimizeMutation.isPending}
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
                id="voice-prompt"
                value={voicePrompt}
                onChange={(event) => setVoicePrompt(event.target.value)}
                placeholder={t("voice.promptPlaceholder")}
                className="min-h-36 resize-none rounded-xl text-xs"
              />
            </div>
            <div className="space-y-2">
              <div className="flex h-7 items-center justify-between gap-2">
                <label htmlFor="voice-preview-text" className="text-xs font-semibold text-foreground/90">
                  {t("voice.previewText")}
                </label>
                <span className="text-[11px] text-muted-foreground">{t("voice.previewTextHint")}</span>
              </div>
              <Textarea
                id="voice-preview-text"
                value={previewText}
                onChange={(event) => setPreviewText(event.target.value)}
                placeholder={t("voice.previewTextPlaceholder")}
                className="min-h-36 resize-none rounded-xl text-xs"
              />
            </div>
          </div>

          <div className="flex justify-end">
            <Button
              className="min-w-36"
              onClick={designMutation.isPending ? stopGeneration : startGeneration}
              disabled={!canGenerate && !designMutation.isPending}
              variant={designMutation.isPending ? "destructive" : "default"}
            >
              {designMutation.isPending ? <Square className="size-3.5 fill-current" /> : <Sparkles className="size-4" />}
              {designMutation.isPending ? t("common.stopGeneration") : t("voice.generatePreview")}
            </Button>
          </div>

          <div className="min-h-60 border-t border-border/70 pt-6">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <div className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Volume2 className="size-4" />
                </div>
                <h2 className="text-sm font-bold">{t("voice.preview")}</h2>
              </div>
              <div className="flex items-center gap-2">
                {previewVoice ? <Badge variant="outline" className="text-xs">{previewVoice.targetModel}</Badge> : null}
                {previewVoice && previewVoice.previewAudioUrl ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-8 gap-1.5 text-xs font-medium cursor-pointer"
                    onClick={() => setPreviewModalOpen(true)}
                  >
                    <Maximize2 className="size-3.5 text-primary" />
                    <span>{t("voice.enlargeAudition")}</span>
                  </Button>
                ) : null}
              </div>
            </div>

            <div className="mt-4 flex min-h-52 items-center justify-center rounded-2xl border border-border/70 bg-card/40 p-6 shadow-inner backdrop-blur-md">
              {designMutation.isPending ? (
                <div className="text-center space-y-3">
                  <div className="relative mx-auto flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                    <AudioLines className="size-7 animate-pulse text-primary" />
                    <span className="absolute inset-0 size-14 animate-ping rounded-2xl bg-primary/20 opacity-40" />
                  </div>
                  <p className="text-sm font-bold text-foreground">{t("voice.generating")}</p>
                  <p className="text-xs text-muted-foreground">{t("voice.generatingHint")}</p>
                </div>
              ) : previewVoice ? (
                <div className="w-full max-w-3xl space-y-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex items-start gap-3.5 min-w-0">
                      <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-primary/15 text-primary shadow-xs">
                        <Volume2 className="size-5" />
                      </span>
                      <div className="min-w-0">
                        <p className="truncate text-base font-bold text-foreground">
                          {previewVoice.name || previewVoice.voiceId}
                        </p>
                        <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground font-mono">
                          {previewVoice.voicePrompt}
                        </p>
                      </div>
                    </div>
                    {previewVoice.previewAudioUrl ? (
                      <div className="flex items-center gap-2 shrink-0">
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8 gap-1.5 text-xs cursor-pointer"
                          onClick={() => copyPrompt(previewVoice.voicePrompt)}
                        >
                          {copied ? <Check className="size-3.5 text-emerald-500" /> : <Copy className="size-3.5" />}
                          {copied ? t("voice.copiedPrompt") : t("voice.copyPrompt")}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8 gap-1.5 text-xs cursor-pointer"
                          onClick={() => downloadAudio(artifactBffUrl(previewVoice.previewAudioUrl!), `${previewVoice.name || "voice"}.wav`)}
                        >
                          <Download className="size-3.5" />
                          {t("voice.downloadAudio")}
                        </Button>
                      </div>
                    ) : null}
                  </div>

                  {previewVoice.previewAudioUrl ? (
                    <div className="rounded-xl border border-border/70 bg-muted/30 p-3 shadow-inner">
                      <audio src={artifactBffUrl(previewVoice.previewAudioUrl)} controls className="w-full" />
                    </div>
                  ) : null}

                  {draftVoice ? (
                    <div className="flex items-center justify-between gap-3 border-t border-border/60 pt-4">
                      <p className="text-xs text-muted-foreground">{t("voice.draftHint")}</p>
                      <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending} className="cursor-pointer">
                        {saveMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                        {saveMutation.isPending ? t("common.saving") : t("voice.save")}
                      </Button>
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="text-center text-muted-foreground space-y-2">
                  <div className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-muted/60 text-muted-foreground">
                    <AudioLines className="size-6 opacity-60" />
                  </div>
                  <p className="text-sm font-semibold text-foreground">{t("voice.previewEmpty")}</p>
                  <p className="text-xs text-muted-foreground">{t("voice.emptyPreviewHint")}</p>
                </div>
              )}
            </div>
          </div>

          {/* 音色大屏试听与参数详情 Dialog */}
          <Dialog open={previewModalOpen} onOpenChange={setPreviewModalOpen}>
            <DialogContent className="w-[94vw] max-w-3xl rounded-2xl border border-border/80 p-0 overflow-hidden shadow-2xl bg-background">
              <DialogHeader className="p-4 px-5 border-b border-border/70 flex flex-row items-center justify-between bg-card/40 shrink-0">
                <div className="flex items-center gap-3">
                  <div className="flex size-8 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <Volume2 className="size-4.5" />
                  </div>
                  <div>
                    <DialogTitle className="text-base font-bold">
                      {previewVoice?.name || t("voice.modalTitle")}
                    </DialogTitle>
                    <DialogDescription className="text-xs">
                      {t("voice.modalDesc")}
                    </DialogDescription>
                  </div>
                </div>
              </DialogHeader>

              {previewVoice ? (
                <div className="p-6 space-y-6">
                  {/* 声波播放区 */}
                  <div className="flex flex-col items-center justify-center rounded-2xl border border-border/70 bg-muted/20 p-6 space-y-4 shadow-inner">
                    <div className="flex items-center justify-center gap-1.5 h-12 w-full max-w-md">
                      <div className="w-1.5 h-6 bg-primary/60 rounded-full animate-pulse" />
                      <div className="w-1.5 h-10 bg-primary/80 rounded-full animate-pulse" style={{ animationDelay: "150ms" }} />
                      <div className="w-1.5 h-8 bg-primary rounded-full animate-pulse" style={{ animationDelay: "300ms" }} />
                      <div className="w-1.5 h-12 bg-primary rounded-full animate-pulse" style={{ animationDelay: "75ms" }} />
                      <div className="w-1.5 h-7 bg-primary/80 rounded-full animate-pulse" style={{ animationDelay: "225ms" }} />
                      <div className="w-1.5 h-11 bg-primary/90 rounded-full animate-pulse" style={{ animationDelay: "400ms" }} />
                      <div className="w-1.5 h-5 bg-primary/60 rounded-full animate-pulse" style={{ animationDelay: "100ms" }} />
                      <div className="w-1.5 h-9 bg-primary/75 rounded-full animate-pulse" style={{ animationDelay: "350ms" }} />
                    </div>

                    {previewVoice.previewAudioUrl ? (
                      <audio src={artifactBffUrl(previewVoice.previewAudioUrl)} controls autoPlay className="w-full max-w-lg" />
                    ) : null}
                  </div>

                  {/* 详细参数 */}
                  <div className="space-y-4">
                    <div className="space-y-1.5">
                      <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block">
                        {t("voice.promptDetailTitle")}
                      </span>
                      <div className="rounded-xl border border-border/70 bg-card/60 p-3.5 text-xs leading-relaxed font-mono text-foreground whitespace-pre-wrap">
                        {previewVoice.voicePrompt}
                      </div>
                    </div>

                    {previewText.trim() ? (
                      <div className="space-y-1.5">
                        <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block">
                          {t("voice.scriptDetailTitle")}
                        </span>
                        <div className="rounded-xl border border-border/70 bg-muted/40 p-3 text-xs leading-relaxed text-muted-foreground">
                          {previewText}
                        </div>
                      </div>
                    ) : null}
                  </div>

                  <div className="flex items-center justify-end gap-3 pt-3 border-t border-border/70">
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-2 cursor-pointer"
                      onClick={() => copyPrompt(previewVoice.voicePrompt)}
                    >
                      {copied ? <Check className="size-4 text-emerald-500" /> : <Copy className="size-4" />}
                      {copied ? t("voice.copiedPromptFull") : t("voice.copyPrompt")}
                    </Button>
                    {previewVoice.previewAudioUrl ? (
                      <Button
                        size="sm"
                        className="gap-2 cursor-pointer"
                        onClick={() => downloadAudio(artifactBffUrl(previewVoice.previewAudioUrl!), `${previewVoice.name || "voice"}.wav`)}
                      >
                        <Download className="size-4" />
                        {t("voice.downloadFullAudio")}
                      </Button>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </DialogContent>
          </Dialog>

          {errorMessage ? (
            <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
              {errorMessage}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
