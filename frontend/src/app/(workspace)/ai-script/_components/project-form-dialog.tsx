"use client";

import { useMutation } from "@tanstack/react-query";
import { ImagePlus, Loader2, Sparkles, Trash2, Upload, X } from "lucide-react";
import Image from "next/image";
import { useRef, useState } from "react";

import {
  createProjectAction,
  generateCoverAction,
  optimizeDescriptionAction,
  setProjectCoverAction,
  clearProjectCoverAction,
  updateProjectAction,
} from "@/actions/projects-actions";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { IMAGE_TYPES, readImageFile } from "@/lib/image-file";
import type { Project } from "@/types/project";

interface ProjectFormProps {
  /** Null puts the form in create mode. */
  project: Project | null;
  onSaved: (project: Project) => void;
  onClose: () => void;
}

/**
 * Split out from the dialog and mounted under a key so its fields initialise from `project`
 * once. Seeding them from an effect instead would fight the React Compiler's rule against
 * synchronous setState in effects, and would re-run on every parent render.
 */
function ProjectForm({ project, onSaved, onClose }: ProjectFormProps) {
  const { t } = useI18n();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState(project?.title ?? "");
  const [description, setDescription] = useState(project?.description ?? "");
  /**
   * What the preview shows: a data URL when the user just picked or generated one, the
   * project's signed URL when it is what was already stored. `coverData` being set is what
   * marks it as needing a write on save.
   */
  const [coverPreview, setCoverPreview] = useState<string | null>(project?.coverImageUrl ?? null);
  const [coverData, setCoverData] = useState<string | null>(null);
  const [coverCleared, setCoverCleared] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const optimizeMutation = useMutation({
    mutationFn: () => optimizeDescriptionAction({ title: title.trim(), description: description.trim() }),
    onSuccess: (response) => setDescription(response.description),
    onError: (error) => setMessage(resolveRequestError(error, t("home.optimizeDescriptionFailed"))),
  });

  const coverMutation = useMutation({
    mutationFn: () => generateCoverAction({ title: title.trim(), description: description.trim() }),
    onSuccess: (response) => {
      setCoverPreview(response.imageData);
      setCoverData(response.imageData);
      setCoverCleared(false);
    },
    onError: (error) => setMessage(resolveRequestError(error, t("home.generateCoverFailed"))),
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = { title: title.trim(), description: description.trim() };
      let saved = project
        ? (await updateProjectAction(project.id, payload)).project
        : (await createProjectAction(payload)).project;
      // The cover is its own endpoint because it is bytes, not fields, so it is applied as
      // a second write once the project has an id to hang it on.
      if (coverData) {
        saved = (await setProjectCoverAction(saved.id, { imageData: coverData })).project;
      } else if (coverCleared && project?.coverImageUrl) {
        saved = (await clearProjectCoverAction(saved.id)).project;
      }
      return saved;
    },
    onSuccess: (saved) => {
      onSaved(saved);
      onClose();
    },
    onError: (error) =>
      setMessage(resolveRequestError(error, project ? t("home.saveProjectFailed") : t("home.createProjectFailed"))),
  });

  const pickCover = async (file: File | undefined) => {
    if (!file) return;
    const result = await readImageFile(file);
    if (!result.ok) {
      setMessage(
        result.reason === "unsupported"
          ? t("home.coverUnsupported")
          : result.reason === "too-large"
            ? t("home.coverTooLarge")
            : t("home.coverUploadFailed")
      );
      return;
    }
    setCoverPreview(result.dataUrl);
    setCoverData(result.dataUrl);
    setCoverCleared(false);
    setMessage(null);
  };

  const busy = saveMutation.isPending || optimizeMutation.isPending || coverMutation.isPending;
  const canGenerateCover = Boolean(title.trim() || description.trim());

  return (
    <>
      <DialogHeader>
        <DialogTitle>{project ? t("home.editProjectTitle") : t("home.createProject")}</DialogTitle>
        <DialogDescription>{t("home.projectDescriptionPlaceholder")}</DialogDescription>
      </DialogHeader>

      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          saveMutation.mutate();
        }}
      >
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="projectTitle">{t("home.projectTitle")}</FieldLabel>
            <Input
              id="projectTitle"
              value={title}
              maxLength={80}
              required
              placeholder={t("home.projectTitlePlaceholder")}
              onChange={(event) => setTitle(event.target.value)}
            />
          </Field>

          <Field>
            <FieldLabel htmlFor="projectDescription">{t("home.projectDescription")}</FieldLabel>
            <Textarea
              id="projectDescription"
              value={description}
              maxLength={4000}
              rows={4}
              placeholder={t("home.projectDescriptionPlaceholder")}
              onChange={(event) => setDescription(event.target.value)}
            />
            <div className="flex justify-end">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busy || !description.trim()}
                onClick={() => optimizeMutation.mutate()}
              >
                {optimizeMutation.isPending ? (
                  <Loader2 data-icon="inline-start" className="animate-spin" />
                ) : (
                  <Sparkles data-icon="inline-start" />
                )}
                {optimizeMutation.isPending ? t("home.optimizingDescription") : t("home.optimizeDescription")}
              </Button>
            </div>
          </Field>

          <Field>
            <FieldLabel>{t("home.projectCover")}</FieldLabel>
            <div className="flex items-start gap-3">
              <span className="relative flex h-24 w-[168px] shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border/60 bg-muted">
                {coverPreview ? (
                  <Image src={coverPreview} alt="" fill unoptimized sizes="168px" className="object-cover" />
                ) : (
                  <ImagePlus className="size-6 text-muted-foreground" />
                )}
              </span>
              <div className="flex flex-wrap gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={IMAGE_TYPES.join(",")}
                  className="hidden"
                  onChange={(event) => {
                    void pickCover(event.target.files?.[0]);
                    event.target.value = "";
                  }}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload data-icon="inline-start" />
                  {t("home.uploadCover")}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={busy || !canGenerateCover}
                  title={canGenerateCover ? undefined : t("home.generateCoverNeedsContent")}
                  onClick={() => coverMutation.mutate()}
                >
                  {coverMutation.isPending ? (
                    <Loader2 data-icon="inline-start" className="animate-spin" />
                  ) : (
                    <Sparkles data-icon="inline-start" />
                  )}
                  {coverMutation.isPending ? t("home.generatingCover") : t("home.generateCover")}
                </Button>
                {coverPreview ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={busy}
                    onClick={() => {
                      setCoverPreview(null);
                      setCoverData(null);
                      setCoverCleared(true);
                    }}
                  >
                    <Trash2 data-icon="inline-start" />
                    {t("home.removeCover")}
                  </Button>
                ) : null}
              </div>
            </div>
          </Field>
        </FieldGroup>

        {message ? <p className="text-sm text-amber-600">{message}</p> : null}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
            <X data-icon="inline-start" />
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={busy || !title.trim()}>
            {saveMutation.isPending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : null}
            {saveMutation.isPending
              ? project
                ? t("common.saving")
                : t("home.creatingProject")
              : t("common.save")}
          </Button>
        </div>
      </form>
    </>
  );
}

export interface ProjectFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Null opens the dialog in create mode. */
  project: Project | null;
  onSaved: (project: Project) => void;
}

export function ProjectFormDialog({ open, onOpenChange, project, onSaved }: ProjectFormDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        {/* Keyed remount is what resets the form between "new" and each project it edits. */}
        {open ? (
          <ProjectForm
            key={project?.id ?? "new"}
            project={project}
            onSaved={onSaved}
            onClose={() => onOpenChange(false)}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
