"use client";

import { useMutation } from "@tanstack/react-query";
import { Download, ImageIcon, RotateCcw, Sparkles, Upload, X } from "lucide-react";
import Image from "next/image";
import { useEffect, useMemo, useRef, useState } from "react";

import { generateImageAction } from "@/actions/image-generation-actions";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { configName } from "@/lib/config-format";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { UserConfig } from "@/types/auth";
import type { GenerateImageInput, ImageReferenceInput } from "@/types/image-generation";

const resolutions: GenerateImageInput["resolution"][] = ["1K", "2K", "4K"];
const ratios: GenerateImageInput["ratio"][] = [
  "auto",
  "1:1",
  "2:3",
  "3:2",
  "3:4",
  "4:3",
  "16:9",
  "9:16",
  "21:9",
  "9:21",
];
const historyStorageKey = "sceneflow-image-generation-history";

interface ImageHistoryItem {
  id: string;
  imageUrl: string;
  prompt: string;
  createdAt: string;
}

function configSelectValue(config: UserConfig) {
  return `${config.source}:${config.id}`;
}

function selectedConfigPayload(config: UserConfig | undefined) {
  if (!config) {
    return {};
  }
  return config.source === "official" ? { officialConfigId: config.id } : { configId: config.id };
}

function isImageConfig(config: UserConfig) {
  return (
    (config.purpose === "image" || (config.purpose === "general" && ["openai", "gemini"].includes(config.provider))) &&
    config.isEnabled &&
    config.isVerified &&
    config.modelSeries.trim()
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

function imageExtension(blob: Blob, url: string) {
  const fromType = blob.type.split("/")[1]?.split(";")[0];
  if (fromType) {
    return fromType === "jpeg" ? "jpg" : fromType;
  }
  try {
    return new URL(url, window.location.href).pathname.split(".").pop() || "png";
  } catch {
    return "png";
  }
}

function readImageHistory() {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const parsed = JSON.parse(window.localStorage.getItem(historyStorageKey) || "[]");
    return Array.isArray(parsed) ? (parsed as ImageHistoryItem[]) : [];
  } catch {
    return [];
  }
}

function saveImageHistory(items: ImageHistoryItem[]) {
  window.localStorage.setItem(historyStorageKey, JSON.stringify(items.slice(0, 20)));
}

interface ImageGenerationPanelProps {
  configs: UserConfig[];
  officialConfigs: UserConfig[];
}

export function ImageGenerationPanel({ configs, officialConfigs }: ImageGenerationPanelProps) {
  const { t, formatDateTime } = useI18n();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedConfigId, setSelectedConfigId] = useState("");
  const [resolution, setResolution] = useState<GenerateImageInput["resolution"]>("1K");
  const [ratio, setRatio] = useState<GenerateImageInput["ratio"]>("auto");
  const [prompt, setPrompt] = useState("");
  const [references, setReferences] = useState<ImageReferenceInput[]>([]);
  const [imageUrl, setImageUrl] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [isDownloading, setIsDownloading] = useState(false);
  const [history, setHistory] = useState<ImageHistoryItem[]>(readImageHistory);

  const imageConfigs = useMemo(
    () => [...officialConfigs.filter(isImageConfig), ...configs.filter(isImageConfig)],
    [configs, officialConfigs]
  );
  const defaultConfigId = useMemo(() => {
    const config = imageConfigs.find((item) => item.isActive) ?? imageConfigs[0];
    return config ? configSelectValue(config) : "";
  }, [imageConfigs]);
  const effectiveConfigId = imageConfigs.some((config) => configSelectValue(config) === selectedConfigId) ? selectedConfigId : defaultConfigId;
  const selectedConfig = imageConfigs.find((config) => configSelectValue(config) === effectiveConfigId);

  const generateMutation = useMutation({
    mutationFn: generateImageAction,
    onSuccess: (response, variables) => {
      const item = {
        id: `${Date.now()}`,
        imageUrl: response.image.url,
        prompt: variables.prompt,
        createdAt: new Date().toISOString(),
      };
      const nextHistory = [item, ...history].slice(0, 20);
      setImageUrl(response.image.url);
      setHistory(nextHistory);
      saveImageHistory(nextHistory);
      setErrorMessage(null);
    },
    onError: (error) => {
      setErrorMessage(resolveRequestError(error, t("images.generateFailed")));
    },
  });

  useEffect(() => {
    if (!generateMutation.isPending) {
      return;
    }

    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [generateMutation.isPending]);

  const addReferences = async (files: FileList | null) => {
    if (!files) {
      return;
    }
    setErrorMessage(null);
    const next = [...references];
    for (const file of Array.from(files).slice(0, 4 - next.length)) {
      if (!file.type.startsWith("image/") || file.size > 10 * 1024 * 1024) {
        setErrorMessage(t("images.referenceLimit"));
        continue;
      }
      next.push({ name: file.name, data: await readFileAsDataUrl(file) });
    }
    setReferences(next);
  };

  const generate = () => {
    const content = prompt.trim();
    if (!content || !selectedConfig || generateMutation.isPending) {
      return;
    }
    setElapsedSeconds(0);
    generateMutation.mutate({
      prompt: content,
      resolution,
      ratio,
      references,
      ...selectedConfigPayload(selectedConfig),
    });
  };

  const downloadImage = async () => {
    if (!imageUrl || isDownloading) {
      return;
    }

    setIsDownloading(true);
    setErrorMessage(null);

    try {
      const response = await fetch(imageUrl);
      if (!response.ok) {
        throw new Error(`Download failed: ${response.status}`);
      }

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = `sceneflow-image-${Date.now()}.${imageExtension(blob, imageUrl)}`;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    } catch {
      setErrorMessage(t("images.downloadFailed"));
    } finally {
      setIsDownloading(false);
    }
  };

  const generatingLabel = t("images.generatingImageWithSeconds", { seconds: elapsedSeconds });

  return (
    <div className="grid min-h-0 flex-1 bg-background md:grid-cols-[360px_minmax(0,1fr)]">
      <aside className="flex min-h-0 flex-col border-b border-border/60 bg-muted/20 p-4 md:border-r md:border-b-0">
        <div className="flex items-center gap-2">
          <Sparkles className="size-4" />
          <h2 className="text-sm font-semibold">{t("home.images")}</h2>
        </div>

        <div className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t("images.model")}</label>
            <Select value={effectiveConfigId} onValueChange={(value) => setSelectedConfigId(value ?? "")}>
              <SelectTrigger>
                <SelectValue placeholder={t("images.selectModel")}>{selectedConfig ? configName(selectedConfig, t) : undefined}</SelectValue>
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                {imageConfigs.map((config) => (
                  <SelectItem key={configSelectValue(config)} value={configSelectValue(config)}>
                    {configName(config, t)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {imageConfigs.length === 0 ? <p className="text-xs text-amber-600">{t("images.noModel")}</p> : null}
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t("images.resolution")}</label>
            <Select value={resolution} onValueChange={(value) => setResolution(value as GenerateImageInput["resolution"])}>
              <SelectTrigger>
                <SelectValue>{resolution}</SelectValue>
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                {resolutions.map((item) => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t("images.ratio")}</label>
            <Select value={ratio} onValueChange={(value) => setRatio(value as GenerateImageInput["ratio"])}>
              <SelectTrigger>
                <SelectValue>{ratio === "auto" ? t("images.auto") : ratio}</SelectValue>
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false} className="max-h-64">
                {ratios.map((item) => (
                  <SelectItem key={item} value={item}>
                    {item === "auto" ? t("images.auto") : item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs leading-5 text-muted-foreground">{t("images.autoHint")}</p>
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t("images.prompt")}</label>
            <Textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder={t("images.promptPlaceholder")}
              className="min-h-28 resize-none"
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <label className="text-sm font-medium">{t("images.references")}</label>
              <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{references.length ? t("images.imageToImage") : t("images.textToImage")}</span>
            </div>
            <div className="flex gap-2">
              <Button type="button" variant="secondary" onClick={() => fileInputRef.current?.click()} disabled={references.length >= 4}>
                <Upload className="size-4" />
                {t("images.uploadReference")}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setReferences([])} disabled={references.length === 0}>
                {t("images.clearReferences")}
              </Button>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              multiple
              className="hidden"
              onChange={(event) => {
                addReferences(event.target.files);
                event.currentTarget.value = "";
              }}
            />
            <div className="grid grid-cols-2 gap-2">
              {Array.from({ length: 4 }).map((_, index) => {
                const reference = references[index];
                return (
                  <div
                    key={index}
                    className={cn(
                      "relative flex aspect-[2/1] items-center justify-center overflow-hidden rounded-md border border-dashed text-xs text-muted-foreground",
                      reference ? "border-border bg-background" : "border-muted-foreground/50"
                    )}
                  >
                    {reference ? (
                      <>
                        <Image src={reference.data} alt="" fill unoptimized sizes="180px" className="object-cover" />
                        <button
                          type="button"
                          onClick={() => setReferences((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                          className="absolute top-1 right-1 inline-flex size-6 items-center justify-center rounded-md bg-background/85 text-foreground"
                          aria-label={t("images.removeReference")}
                        >
                          <X className="size-3.5" />
                        </button>
                      </>
                    ) : (
                      t("images.emptySlot", { index: index + 1 })
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <div className="mt-4 border-t border-border/70 pt-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">{t("images.history")}</h3>
            <span className="text-xs text-muted-foreground">{history.length}</span>
          </div>
          {history.length ? (
            <div className="max-h-56 space-y-2 overflow-y-auto pr-1">
              {history.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setImageUrl(item.imageUrl)}
                  className="flex w-full gap-2 rounded-md border border-border/70 bg-background/60 p-2 text-left transition-colors hover:bg-muted/60"
                  aria-label={t("images.viewHistoryItem")}
                >
                  <span className="relative size-14 shrink-0 overflow-hidden rounded-md bg-muted">
                    <Image src={item.imageUrl} alt="" fill unoptimized sizes="56px" className="object-cover" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-medium">{item.prompt}</span>
                    <span className="mt-1 block text-xs text-muted-foreground">{formatDateTime(item.createdAt)}</span>
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">{t("images.historyEmpty")}</p>
          )}
        </div>

        <div className="mt-4 border-t border-border/70 pt-4">
          <Button className="w-full" onClick={generate} disabled={!prompt.trim() || !selectedConfig || generateMutation.isPending}>
            <Sparkles className="size-4" />
            {generateMutation.isPending ? generatingLabel : t("images.generateNow")}
          </Button>
        </div>
      </aside>

      <section className="flex min-h-0 min-w-0 flex-col p-4 md:p-6">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">{t("images.preview")}</h2>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={generate} disabled={!imageUrl || generateMutation.isPending}>
              <RotateCcw className="size-4" />
              {t("images.regenerate")}
            </Button>
            {imageUrl ? (
              <Button variant="secondary" size="sm" onClick={downloadImage} disabled={isDownloading}>
                <Download className="size-4" />
                {t("images.download")}
              </Button>
            ) : (
              <Button variant="secondary" size="sm" disabled>
                <Download className="size-4" />
                {t("images.download")}
              </Button>
            )}
          </div>
        </div>

        <div className="mt-4 flex min-h-0 flex-1 items-center justify-center rounded-md border border-dashed border-muted-foreground/50 bg-muted/10">
          {generateMutation.isPending ? (
            <div className="text-center text-sm text-muted-foreground">
              <Sparkles className="mx-auto mb-3 size-5 animate-pulse" />
              {generatingLabel}
            </div>
          ) : imageUrl ? (
            <div className="relative h-full w-full">
              <Image src={imageUrl} alt={t("images.resultAlt")} fill unoptimized sizes="(min-width: 768px) calc(100vw - 720px), 100vw" className="object-contain" />
            </div>
          ) : (
            <div className="text-center text-sm text-muted-foreground">
              <ImageIcon className="mx-auto mb-3 size-5" />
              {t("images.emptyPreview")}
            </div>
          )}
        </div>
        {errorMessage ? <p className="mt-3 text-sm text-amber-600">{errorMessage}</p> : null}
      </section>
    </div>
  );
}
