"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { isCancel } from "axios";
import { Loader2, Save, Sparkles, Square, Trash2 } from "lucide-react";
import Image from "next/image";
import { useRef, useState } from "react";

import {
  clearProjectCoverAction,
  generateCoverAction,
  setProjectCoverAction,
  updateProjectAction,
} from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { PromptField } from "@/components/prompt-field";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { Project } from "@/types/project";

import { ReferenceImage } from "./reference-image";

/**
 * The cover, edited in place. Unlike the create dialog it writes immediately — there is a
 * project to write to, and nothing else on this page is waiting on the bytes.
 */
export function ProjectCoverField({ project }: { project: Project }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [coverPrompt, setCoverPrompt] = useState(project.coverPrompt);
  const [message, setMessage] = useState<string | null>(null);
  const coverController = useRef<AbortController | null>(null);

  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.projects });

  const uploadMutation = useMutation({
    mutationFn: (imageData: string) => setProjectCoverAction(project.id, { imageData }),
    onSuccess: () => {
      setMessage(null);
      void refresh();
    },
    onError: (error) => setMessage(resolveRequestError(error, t("home.coverUploadFailed"))),
  });

  const savePromptMutation = useMutation({
    mutationFn: () => updateProjectAction(project.id, { coverPrompt: coverPrompt.trim() }),
    onSuccess: () => {
      setMessage(null);
      void refresh();
    },
    onError: (error) => setMessage(resolveRequestError(error, t("home.saveProjectFailed"))),
  });

  const generateMutation = useMutation({
    mutationFn: async () => {
      const drawn = await generateCoverAction(
        { prompt: coverPrompt.trim(), title: project.title },
        coverController.current?.signal
      );
      return setProjectCoverAction(project.id, { imageData: drawn.imageData });
    },
    onSuccess: () => {
      setMessage(null);
      void refresh();
    },
    onError: (error) => {
      if (isCancel(error)) return;
      setMessage(resolveRequestError(error, t("home.generateCoverFailed")));
    },
    onSettled: () => {
      coverController.current = null;
    },
  });

  const stopGenerate = () => {
    coverController.current?.abort();
    coverController.current = null;
    generateMutation.reset();
  };

  const startGenerate = () => {
    coverController.current = new AbortController();
    generateMutation.mutate();
  };

  const clearMutation = useMutation({
    mutationFn: () => clearProjectCoverAction(project.id),
    onSuccess: () => void refresh(),
    onError: (error) => setMessage(resolveRequestError(error, t("reference.deleteFailed"))),
  });

  const busy = uploadMutation.isPending || generateMutation.isPending || clearMutation.isPending;
  const promptDirty = coverPrompt.trim() !== project.coverPrompt;

  return (
    <Field>
      <FieldLabel>{t("home.projectCover")}</FieldLabel>

      <PromptField
        id="projectInfoCoverPrompt"
        label={t("home.coverPrompt")}
        kind="cover"
        presetKind="cover"
        value={coverPrompt}
        onChange={setCoverPrompt}
        placeholder={t("home.coverPromptPlaceholder")}
        busy={busy}
        onError={setMessage}
        actions={
          promptDirty ? (
            <Button
              type="button"
              variant="outline"
              size="xs"
              disabled={savePromptMutation.isPending}
              onClick={() => savePromptMutation.mutate()}
              className="h-7 gap-1 text-[11px] cursor-pointer"
            >
              {savePromptMutation.isPending ? (
                <Loader2 data-icon="inline-start" className="size-3 animate-spin" />
              ) : (
                <Save data-icon="inline-start" className="size-3" />
              )}
              {t("common.save")}
            </Button>
          ) : null
        }
      />

      <div className="mt-3 max-w-sm">
        <ReferenceImage
          url={project.coverImageUrl}
          generateLabel={t("home.generateCover")}
          generatingLabel={t("home.generatingCover")}
          uploadLabel={t("home.uploadCover")}
          busy={busy}
          generating={generateMutation.isPending}
          // The cover has a subject only once the user has described one.
          generateDisabled={!coverPrompt.trim()}
          generateTitle={coverPrompt.trim() ? undefined : t("home.coverPromptRequired")}
          onGenerate={startGenerate}
          onStop={stopGenerate}
          onUpload={(dataUrl) => uploadMutation.mutate(dataUrl)}
          onError={setMessage}
        />
        {project.coverImageUrl ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="mt-2"
            disabled={busy}
            onClick={() => clearMutation.mutate()}
          >
            <Trash2 data-icon="inline-start" />
            {t("home.removeCover")}
          </Button>
        ) : null}
      </div>
      {message ? <p className="text-sm text-amber-600">{message}</p> : null}
    </Field>
  );
}

/** Re-exported so the cast/prop sheet previews and this field share one look. */
export function SheetPreview({ url, emptyLabel }: { url: string | null; emptyLabel: string }) {
  return (
    <span className="relative flex aspect-[3/2] w-full items-center justify-center overflow-hidden rounded-lg border border-border/60 bg-muted">
      {url ? (
        <Image src={url} alt="" fill unoptimized sizes="(min-width: 768px) 50vw, 100vw" className="object-contain" />
      ) : (
        <span className="px-4 text-center text-xs text-muted-foreground">{emptyLabel}</span>
      )}
    </span>
  );
}

/** Kept next to the preview so both sheet pages show a merge button with the same states. */
export function MergeButton({
  label,
  pendingLabel,
  pending,
  disabled,
  onClick,
}: {
  label: string;
  pendingLabel: string;
  pending: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <Button type="button" disabled={pending || disabled} onClick={onClick}>
      {pending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Sparkles data-icon="inline-start" />}
      {pending ? pendingLabel : label}
    </Button>
  );
}

/** A generate button that turns into a stop button while its request is in flight. */
export function GenerateStopButton({
  label,
  stopLabel,
  pending,
  disabled,
  title,
  onStart,
  onStop,
  size = "sm",
}: {
  label: string;
  stopLabel: string;
  pending: boolean;
  disabled?: boolean;
  title?: string;
  onStart: () => void;
  onStop: () => void;
  size?: "xs" | "sm" | "default";
}) {
  return (
    <Button
      type="button"
      size={size}
      variant={pending ? "destructive" : "default"}
      // Stopping stays available while it runs; only starting can be disabled.
      disabled={pending ? false : disabled}
      title={title}
      onClick={pending ? onStop : onStart}
      className={cn("cursor-pointer transition-colors", pending && "animate-pulse font-medium")}
    >
      {pending ? (
        <Square data-icon="inline-start" className="size-3 fill-current" />
      ) : (
        <Sparkles data-icon="inline-start" />
      )}
      {pending ? stopLabel : label}
    </Button>
  );
}
