"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Sparkles, Trash2 } from "lucide-react";
import Image from "next/image";
import { useState } from "react";

import {
  clearProjectCoverAction,
  generateCoverAction,
  setProjectCoverAction,
} from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import type { Project } from "@/types/project";

import { ReferenceImage } from "./reference-image";

/**
 * The cover, edited in place. Unlike the create dialog it writes immediately — there is a
 * project to write to, and nothing else on this page is waiting on the bytes.
 */
export function ProjectCoverField({ project }: { project: Project }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);

  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.projects });

  const uploadMutation = useMutation({
    mutationFn: (imageData: string) => setProjectCoverAction(project.id, { imageData }),
    onSuccess: () => {
      setMessage(null);
      void refresh();
    },
    onError: (error) => setMessage(resolveRequestError(error, t("home.coverUploadFailed"))),
  });

  const generateMutation = useMutation({
    mutationFn: async () => {
      const drawn = await generateCoverAction({ title: project.title, description: project.description });
      return setProjectCoverAction(project.id, { imageData: drawn.imageData });
    },
    onSuccess: () => {
      setMessage(null);
      void refresh();
    },
    onError: (error) => setMessage(resolveRequestError(error, t("home.generateCoverFailed"))),
  });

  const clearMutation = useMutation({
    mutationFn: () => clearProjectCoverAction(project.id),
    onSuccess: () => void refresh(),
    onError: (error) => setMessage(resolveRequestError(error, t("reference.deleteFailed"))),
  });

  const busy = uploadMutation.isPending || generateMutation.isPending || clearMutation.isPending;

  return (
    <Field>
      <FieldLabel>{t("home.projectCover")}</FieldLabel>
      <div className="max-w-sm">
        <ReferenceImage
          url={project.coverImageUrl}
          generateLabel={t("home.generateCover")}
          generatingLabel={t("home.generatingCover")}
          uploadLabel={t("home.uploadCover")}
          busy={busy}
          generating={generateMutation.isPending}
          onGenerate={() => generateMutation.mutate()}
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
