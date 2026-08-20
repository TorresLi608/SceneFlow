"use client";

import { useMutation } from "@tanstack/react-query";
import { isCancel } from "axios";
import { ImagePlus, Loader2, Sparkles, Square, Trash2, Upload, X } from "lucide-react";
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
import { cn } from "@/lib/utils";
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
  const optimizeController = useRef<AbortController | null>(null);
  const coverController = useRef<AbortController | null>(null);
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

  const stopOptimize = () => {
    optimizeController.current?.abort();
    optimizeController.current = null;
    optimizeMutation.reset();
  };

  const startOptimize = () => {
    optimizeController.current = new AbortController();
    optimizeMutation.mutate();
  };

  const stopCover = () => {
    coverController.current?.abort();
    coverController.current = null;
    coverMutation.reset();
  };

  const startCover = () => {
    coverController.current = new AbortController();
    coverMutation.mutate();
  };

  const optimizeMutation = useMutation({
    mutationFn: () =>
      optimizeDescriptionAction(
        { title: title.trim(), description: description.trim() },
        optimizeController.current?.signal
      ),
    onSuccess: (response) => setDescription(response.description),
    onError: (error) => {
      if (isCancel(error)) return;
      setMessage(resolveRequestError(error, t("home.optimizeDescriptionFailed")));
    },
    onSettled: () => {
      optimizeController.current = null;
    },
  });

  const coverMutation = useMutation({
    mutationFn: () =>
      generateCoverAction(
        { title: title.trim(), description: description.trim() },
        coverController.current?.signal
      ),
    onSuccess: (response) => {
      setCoverPreview(response.imageData);
      setCoverData(response.imageData);
      setCoverCleared(false);
    },
    onError: (error) => {
      if (isCancel(error)) return;
      setMessage(resolveRequestError(error, t("home.generateCoverFailed")));
    },
    onSettled: () => {
      coverController.current = null;
    },
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
      <DialogHeader className="pb-2">
        <DialogTitle className="text-lg font-bold text-foreground">
          {project ? t("home.editProjectTitle") : t("home.createProject")}
        </DialogTitle>
        <DialogDescription className="text-xs text-muted-foreground">
          {t("home.projectDescriptionPlaceholder")}
        </DialogDescription>
      </DialogHeader>

      <form
        className="flex flex-col gap-4 pt-1"
        onSubmit={(event) => {
          event.preventDefault();
          saveMutation.mutate();
        }}
      >
        <FieldGroup className="space-y-4">
          <Field className="space-y-1.5">
            <FieldLabel htmlFor="projectTitle" className="text-xs font-medium text-foreground">
              {t("home.projectTitle")}
            </FieldLabel>
            <Input
              id="projectTitle"
              value={title}
              maxLength={80}
              required
              placeholder={t("home.projectTitlePlaceholder")}
              onChange={(event) => setTitle(event.target.value)}
              className="h-10 rounded-xl text-xs bg-muted/20 focus-visible:bg-background"
            />
          </Field>

          <Field className="space-y-1.5">
            <div className="flex h-7 items-center justify-between">
              <FieldLabel htmlFor="projectDescription" className="text-xs font-medium text-foreground">
                {t("home.projectDescription")}
              </FieldLabel>
              <Button
                type="button"
                variant={optimizeMutation.isPending ? "destructive" : "outline"}
                size="xs"
                disabled={
                  (!description.trim() && !optimizeMutation.isPending) ||
                  saveMutation.isPending ||
                  coverMutation.isPending
                }
                onClick={optimizeMutation.isPending ? stopOptimize : startOptimize}
                className={cn(
                  "h-7 gap-1 text-[11px] rounded-lg cursor-pointer transition-colors",
                  optimizeMutation.isPending && "animate-pulse font-medium"
                )}
                title={
                  optimizeMutation.isPending
                    ? t("home.stopOptimizingDescription")
                    : t("home.optimizeDescription")
                }
              >
                {optimizeMutation.isPending ? (
                  <Square data-icon="inline-start" className="size-2.5 fill-current" />
                ) : (
                  <Sparkles data-icon="inline-start" className="size-3 text-primary" />
                )}
                {optimizeMutation.isPending
                  ? t("home.stopOptimizingDescription")
                  : t("home.optimizeDescription")}
              </Button>
            </div>
            <Textarea
              id="projectDescription"
              value={description}
              maxLength={4000}
              rows={4}
              placeholder={t("home.projectDescriptionPlaceholder")}
              onChange={(event) => setDescription(event.target.value)}
              className="min-h-24 resize-none rounded-xl text-xs bg-muted/20 focus-visible:bg-background leading-relaxed"
            />
          </Field>

          <Field className="space-y-1.5">
            <FieldLabel className="text-xs font-medium text-foreground">
              {t("home.projectCover")}
            </FieldLabel>
            <div className="flex items-start gap-3.5 rounded-2xl border border-border/60 bg-muted/20 p-3">
              <span className="relative flex aspect-[16/10] w-40 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-border/80 bg-muted/60 shadow-inner">
                {coverPreview ? (
                  <Image src={coverPreview} alt="" fill unoptimized sizes="160px" className="object-cover" />
                ) : (
                  <div className="flex flex-col items-center gap-1 text-muted-foreground/60">
                    <ImagePlus className="size-6" />
                    <span className="text-[10px]">16:10 封面</span>
                  </div>
                )}
              </span>

              <div className="flex flex-1 flex-col justify-between self-stretch py-0.5">
                <div>
                  <p className="text-xs font-medium text-foreground">自定义或 AI 渲染封面</p>
                  <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">
                    支持上传 10MB 内的图片，或根据标题与故事简介一键生成专属封面。
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2 pt-2">
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
                    size="xs"
                    disabled={busy}
                    onClick={() => fileInputRef.current?.click()}
                    className="h-7 gap-1 rounded-lg text-xs cursor-pointer"
                  >
                    <Upload data-icon="inline-start" className="size-3" />
                    {t("home.uploadCover")}
                  </Button>
                  <Button
                    type="button"
                    variant={coverMutation.isPending ? "destructive" : "outline"}
                    size="xs"
                    disabled={
                      (!canGenerateCover && !coverMutation.isPending) ||
                      saveMutation.isPending ||
                      optimizeMutation.isPending
                    }
                    title={canGenerateCover ? undefined : t("home.generateCoverNeedsContent")}
                    onClick={coverMutation.isPending ? stopCover : startCover}
                    className={cn(
                      "h-7 gap-1 rounded-lg text-xs cursor-pointer transition-colors",
                      coverMutation.isPending && "animate-pulse font-medium"
                    )}
                  >
                    {coverMutation.isPending ? (
                      <Square data-icon="inline-start" className="size-2.5 fill-current" />
                    ) : (
                      <Sparkles data-icon="inline-start" className="size-3 text-primary" />
                    )}
                    {coverMutation.isPending
                      ? t("home.stopGeneratingCover")
                      : t("home.generateCover")}
                  </Button>
                  {coverPreview ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="xs"
                      disabled={busy}
                      onClick={() => {
                        setCoverPreview(null);
                        setCoverData(null);
                        setCoverCleared(true);
                      }}
                      className="h-7 gap-1 rounded-lg text-xs cursor-pointer text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                    >
                      <Trash2 data-icon="inline-start" className="size-3" />
                      {t("home.removeCover")}
                    </Button>
                  ) : null}
                </div>
              </div>
            </div>
          </Field>
        </FieldGroup>

        {message ? (
          <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-2.5 text-xs text-destructive">
            {message}
          </div>
        ) : null}

        <div className="flex items-center justify-end gap-2 border-t border-border/60 pt-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={onClose}
            className="h-9 rounded-xl text-xs cursor-pointer"
          >
            <X data-icon="inline-start" className="size-3.5" />
            {t("common.cancel")}
          </Button>
          <Button
            type="submit"
            size="sm"
            disabled={busy || !title.trim()}
            className="h-9 rounded-xl px-4 text-xs font-semibold shadow-xs cursor-pointer"
          >
            {saveMutation.isPending ? <Loader2 data-icon="inline-start" className="size-3.5 animate-spin" /> : null}
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
      <DialogContent className="sm:max-w-xl rounded-3xl p-5 sm:p-6 shadow-2xl border-border/80 backdrop-blur-xl">
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
