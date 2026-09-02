"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Save } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";

import {
  getProjectModelsAction,
  listProjectsAction,
  updateProjectAction,
} from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { listUserConfigsAction } from "@/actions/settings-actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { configName } from "@/lib/config-format";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import type { ConfigPurpose, UserConfig } from "@/types/auth";
import type {
  GenerationRatio,
  ImageResolution,
  Project,
  ProjectModelSettings,
  VideoQuality,
} from "@/types/project";

import { ProjectCoverField } from "../_components/project-cover-field";

const IMAGE_RESOLUTIONS: ImageResolution[] = ["1K", "2K", "4K"];
const IMAGE_RATIOS: GenerationRatio[] = ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "16:9", "9:16", "21:9", "9:21"];
/** Fallbacks for a video model that declares no capabilities of its own. */
const VIDEO_QUALITIES: VideoQuality[] = ["480p", "720p", "1080p", "2K", "4K"];
const VIDEO_RATIOS: GenerationRatio[] = ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "adaptive"];

/**
 * "Follow the account default" has to be a real option rather than an absent one, so the
 * value is a string: "" means follow, anything else is a config id. The backend takes 0
 * for the same reason — in a PATCH, `null` already means "leave this field alone".
 */
const FOLLOW_ACCOUNT = "";

function ChoiceSelect({
  id,
  label,
  value,
  options,
  onChange,
  disabled,
}: {
  id: string;
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <Field>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Select items={options} value={value} onValueChange={(next) => onChange(next ?? value)} disabled={disabled}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            {options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
    </Field>
  );
}

/** One model card: which model, where it came from, and what it will not accept. */
function ModelCard({
  title,
  hint,
  configs,
  selected,
  onSelect,
  resolvedLabel,
  isProjectPick,
  limits,
  children,
}: {
  title: string;
  hint?: string;
  configs: UserConfig[];
  selected: string;
  onSelect: (value: string) => void;
  resolvedLabel: string | null;
  isProjectPick: boolean;
  limits: string[];
  children?: React.ReactNode;
}) {
  const { t } = useI18n();
  const items = [
    { value: FOLLOW_ACCOUNT, label: t("workbench.followAccount") },
    ...configs.map((config) => ({ value: String(config.id), label: configName(config, t) })),
  ];

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-border/70 bg-card/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <Badge variant={isProjectPick ? "default" : "outline"} className="text-[10px]">
          {isProjectPick ? t("workbench.projectPick") : t("workbench.accountDefault")}
        </Badge>
      </div>

      <Select items={items} value={selected} onValueChange={(next) => onSelect(next ?? FOLLOW_ACCOUNT)}>
        <SelectTrigger className="w-full" aria-label={title}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            {items.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>

      <p className="text-xs text-muted-foreground">{resolvedLabel ?? t("workbench.modelUnset")}</p>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}

      {limits.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {limits.map((limit) => (
            <Badge key={limit} variant="secondary" className="text-[10px] font-normal">
              {limit}
            </Badge>
          ))}
        </div>
      ) : null}

      {children}
    </section>
  );
}

function ModelSettingsPanel({ project }: { project: Project }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [settings, setSettings] = useState<ProjectModelSettings>(project.modelSettings);
  const [message, setMessage] = useState<string | null>(null);

  const configsQuery = useQuery({
    queryKey: queryKeys.userConfigs,
    queryFn: listUserConfigsAction,
  });
  const modelsQuery = useQuery({
    queryKey: queryKeys.projectModels(project.id),
    queryFn: () => getProjectModelsAction(project.id),
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      updateProjectAction(project.id, {
        // 0, not null: null means "leave alone", so clearing a pick needs a real value.
        modelSettings: {
          ...settings,
          textConfigId: settings.textConfigId ?? 0,
          imageConfigId: settings.imageConfigId ?? 0,
          videoConfigId: settings.videoConfigId ?? 0,
          audioConfigId: settings.audioConfigId ?? 0,
        },
      }),
    onSuccess: () => {
      setMessage(t("workbench.modelSettingsSaved"));
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects });
      void queryClient.invalidateQueries({ queryKey: queryKeys.projectModels(project.id) });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("home.saveProjectFailed"))),
  });

  const byPurpose = (purpose: ConfigPurpose) => {
    const all = [
      ...(configsQuery.data?.officialConfigs ?? []),
      ...(configsQuery.data?.configs ?? []),
    ];
    return all.filter((config) => config.purpose === purpose && config.isEnabled);
  };

  const resolved = modelsQuery.data?.models;
  const describe = (key: "text" | "image" | "video" | "audio") => {
    const summary = resolved?.[key];
    return summary ? `${summary.provider} · ${summary.model}` : null;
  };

  const imageLimits = () => {
    const capabilities = resolved?.image?.capabilities;
    const maximum = capabilities?.maxReferenceImages;
    return maximum ? [t("workbench.limitReferenceImages", { count: maximum })] : [];
  };

  const videoCapabilities = resolved?.video?.capabilities ?? null;
  const videoLimits = () => {
    if (!videoCapabilities) return [];
    const limits: string[] = [
      t("workbench.limitDuration", {
        min: videoCapabilities.minDuration,
        max: videoCapabilities.maxDuration,
      }),
    ];
    if (videoCapabilities.maxReferenceImages > 0) {
      limits.push(t("workbench.limitReferenceImages", { count: videoCapabilities.maxReferenceImages }));
    }
    if (videoCapabilities.maxReferenceVideos > 0) {
      limits.push(t("workbench.limitReferenceVideos", { count: videoCapabilities.maxReferenceVideos }));
    }
    if (videoCapabilities.maxReferenceAudios > 0) {
      limits.push(t("workbench.limitReferenceAudios", { count: videoCapabilities.maxReferenceAudios }));
    }
    return limits;
  };

  // Options come from the model's declared capabilities where it has them, so the panel
  // cannot offer a setting a render would then refuse.
  const videoQualities = videoCapabilities?.qualities?.length ? videoCapabilities.qualities : VIDEO_QUALITIES;
  const videoRatios = videoCapabilities?.aspectRatios?.length ? videoCapabilities.aspectRatios : VIDEO_RATIOS;
  const durations = videoCapabilities
    ? Array.from(
        { length: Math.max(1, videoCapabilities.maxDuration - videoCapabilities.minDuration + 1) },
        (_, index) => videoCapabilities.minDuration + index
      )
    : [3, 4, 5, 6, 8, 10];

  const patch = (values: Partial<ProjectModelSettings>) => setSettings((current) => ({ ...current, ...values }));
  const idValue = (value: number | null) => (value ? String(value) : FOLLOW_ACCOUNT);
  const parseId = (value: string) => (value === FOLLOW_ACCOUNT ? null : Number(value));

  if (configsQuery.isLoading || modelsQuery.isLoading) {
    return <Skeleton className="h-72 rounded-lg" />;
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-sm font-semibold">{t("workbench.modelSettings")}</h2>
        <p className="mt-1 text-xs text-muted-foreground">{t("workbench.modelSettingsHint")}</p>
      </div>

      <ModelCard
        title={t("workbench.modelText")}
        hint={t("workbench.modelTextHint")}
        configs={byPurpose("script")}
        selected={idValue(settings.textConfigId)}
        onSelect={(value) => patch({ textConfigId: parseId(value) })}
        resolvedLabel={describe("text")}
        isProjectPick={Boolean(resolved?.text?.isProjectPick)}
        limits={[]}
      />

      <ModelCard
        title={t("workbench.modelImage")}
        configs={byPurpose("image")}
        selected={idValue(settings.imageConfigId)}
        onSelect={(value) => patch({ imageConfigId: parseId(value) })}
        resolvedLabel={describe("image")}
        isProjectPick={Boolean(resolved?.image?.isProjectPick)}
        limits={imageLimits()}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <ChoiceSelect
            id="imageResolution"
            label={t("workbench.resolution")}
            value={settings.imageResolution}
            options={IMAGE_RESOLUTIONS.map((item) => ({ value: item, label: item }))}
            onChange={(value) => patch({ imageResolution: value as ImageResolution })}
          />
          <ChoiceSelect
            id="imageRatio"
            label={t("workbench.ratio")}
            value={settings.imageRatio}
            options={IMAGE_RATIOS.map((item) => ({ value: item, label: item }))}
            onChange={(value) => patch({ imageRatio: value as GenerationRatio })}
          />
        </div>
      </ModelCard>

      <ModelCard
        title={t("workbench.modelVideo")}
        configs={byPurpose("video")}
        selected={idValue(settings.videoConfigId)}
        onSelect={(value) => patch({ videoConfigId: parseId(value) })}
        resolvedLabel={describe("video")}
        isProjectPick={Boolean(resolved?.video?.isProjectPick)}
        limits={videoLimits()}
      >
        {videoCapabilities ? null : (
          <p className="text-xs text-amber-600">{t("workbench.noVideoCapabilities")}</p>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <ChoiceSelect
            id="videoQuality"
            label={t("workbench.quality")}
            value={settings.videoQuality}
            options={videoQualities.map((item) => ({ value: item, label: item }))}
            onChange={(value) => patch({ videoQuality: value as VideoQuality })}
          />
          <ChoiceSelect
            id="videoAspectRatio"
            label={t("workbench.videoRatio")}
            value={settings.videoAspectRatio}
            options={videoRatios.map((item) => ({ value: item, label: item }))}
            onChange={(value) => patch({ videoAspectRatio: value as GenerationRatio })}
          />
          <ChoiceSelect
            id="videoDuration"
            label={t("workbench.videoDuration")}
            value={String(settings.videoDuration)}
            options={durations.map((item) => ({ value: String(item), label: `${item}s` }))}
            onChange={(value) => patch({ videoDuration: Number(value) })}
          />
        </div>
        {videoCapabilities?.promptExtend ? (
          <Field orientation="horizontal">
            <Switch
              id="videoPromptExtend"
              checked={settings.videoPromptExtend}
              onCheckedChange={(checked) => patch({ videoPromptExtend: checked })}
            />
            <FieldLabel htmlFor="videoPromptExtend">{t("workbench.promptExtend")}</FieldLabel>
          </Field>
        ) : null}
        {videoCapabilities?.audioParam ? (
          <Field orientation="horizontal">
            <Switch
              id="videoAudioEnabled"
              checked={settings.videoAudioEnabled}
              onCheckedChange={(checked) => patch({ videoAudioEnabled: checked })}
            />
            <FieldLabel htmlFor="videoAudioEnabled">
              {videoCapabilities.audioParam === "with_audio" ? t("workbench.outputAudio") : t("workbench.audioGeneration")}
            </FieldLabel>
          </Field>
        ) : null}
      </ModelCard>

      <ModelCard
        title={t("workbench.modelAudio")}
        hint={t("workbench.modelAudioHint")}
        configs={byPurpose("audio")}
        selected={idValue(settings.audioConfigId)}
        onSelect={(value) => patch({ audioConfigId: parseId(value) })}
        resolvedLabel={describe("audio")}
        isProjectPick={Boolean(resolved?.audio?.isProjectPick)}
        limits={[]}
      />

      <div className="flex items-center gap-3">
        <Button type="button" disabled={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
          {saveMutation.isPending ? (
            <Loader2 data-icon="inline-start" className="animate-spin" />
          ) : (
            <Save data-icon="inline-start" />
          )}
          {t("workbench.saveModelSettings")}
        </Button>
        {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
      </div>
    </div>
  );
}

function InfoForm({ project }: { project: Project }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState(project.title);
  const [description, setDescription] = useState(project.description);
  const [seriesBible, setSeriesBible] = useState(project.seriesBible);
  const [message, setMessage] = useState<string | null>(null);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateProjectAction(project.id, {
        title: title.trim(),
        description: description.trim(),
        seriesBible,
      }),
    onSuccess: () => {
      setMessage(t("workbench.infoSaved"));
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("home.saveProjectFailed"))),
  });

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{t("workbench.projectInfo")}</h1>
      </div>

      <form
        className="flex flex-col gap-5"
        onSubmit={(event) => {
          event.preventDefault();
          saveMutation.mutate();
        }}
      >
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="infoTitle">{t("home.projectTitle")}</FieldLabel>
            <Input
              id="infoTitle"
              value={title}
              maxLength={80}
              required
              onChange={(event) => setTitle(event.target.value)}
            />
          </Field>

          <Field>
            <FieldLabel htmlFor="infoDescription">{t("home.projectDescription")}</FieldLabel>
            <Textarea
              id="infoDescription"
              value={description}
              maxLength={4000}
              rows={4}
              placeholder={t("home.projectDescriptionPlaceholder")}
              onChange={(event) => setDescription(event.target.value)}
            />
          </Field>

          <Field>
            <FieldLabel htmlFor="infoSeriesBible">{t("workbench.seriesBible")}</FieldLabel>
            <Textarea
              id="infoSeriesBible"
              value={seriesBible}
              maxLength={200_000}
              rows={6}
              placeholder={t("workbench.seriesBiblePlaceholder")}
              onChange={(event) => setSeriesBible(event.target.value)}
            />
            <FieldDescription>{t("workbench.seriesBibleHint")}</FieldDescription>
          </Field>
        </FieldGroup>

        <div className="flex items-center gap-3">
          <Button type="submit" disabled={saveMutation.isPending || !title.trim()}>
            {saveMutation.isPending ? (
              <Loader2 data-icon="inline-start" className="animate-spin" />
            ) : (
              <Save data-icon="inline-start" />
            )}
            {t("workbench.saveInfo")}
          </Button>
          {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
        </div>
      </form>

      <ProjectCoverField project={project} />

      <ModelSettingsPanel project={project} />
    </div>
  );
}

export default function ProjectInfoPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { t } = useI18n();

  const projectsQuery = useQuery({
    queryKey: queryKeys.projects,
    queryFn: listProjectsAction,
    staleTime: 300_000,
  });
  const project = projectsQuery.data?.projects.find((item) => item.id === projectId);

  if (!project) {
    return projectsQuery.isLoading ? (
      <Skeleton className="h-72 max-w-2xl rounded-lg" />
    ) : (
      <p className="text-sm text-muted-foreground">{t("home.emptyProjects")}</p>
    );
  }

  // Keyed so switching projects re-seeds the form instead of leaving stale field values.
  return <InfoForm key={project.id} project={project} />;
}
