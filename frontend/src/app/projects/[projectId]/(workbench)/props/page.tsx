"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isCancel } from "axios";
import { Loader2, Pencil, Plus, Trash2, X } from "lucide-react";
import { useParams } from "next/navigation";
import { useRef, useState } from "react";

import {
  createPropAction,
  deletePropAction,
  draftPropPromptAction,
  generatePropImageAction,
  listCharactersAction,
  listPropsAction,
  listProjectsAction,
  mergePropSheetAction,
  updatePropAction,
  uploadPropImageAction,
} from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { DraftPromptButton, PromptField } from "@/components/prompt-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import type { Character, Prop } from "@/types/project";

import { MergeButton, SheetPreview } from "../_components/project-cover-field";
import { ReferenceImage } from "../_components/reference-image";

interface PropFormValues {
  name: string;
  description: string;
  ownerCharacterId: string;
}

function PropForm({
  prop,
  characters,
  pending,
  onSubmit,
  onClose,
}: {
  prop: Prop | null;
  characters: Character[];
  pending: boolean;
  onSubmit: (values: PropFormValues) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState(prop?.name ?? "");
  const [description, setDescription] = useState(prop?.description ?? "");
  const [ownerCharacterId, setOwnerCharacterId] = useState(prop?.ownerCharacterId ?? "");

  const ownerItems = [
    { value: "", label: t("prop.ownerNone") },
    ...characters.map((character) => ({ value: character.id, label: character.name })),
  ];

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({ name: name.trim(), description: description.trim(), ownerCharacterId });
      }}
    >
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="propName">{t("prop.name")}</FieldLabel>
          <Input
            id="propName"
            value={name}
            maxLength={80}
            required
            placeholder={t("prop.namePlaceholder")}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="propOwner">{t("prop.owner")}</FieldLabel>
          {/* "" unbinds; the backend reads a JSON null as "leave alone". */}
          <Select
            items={ownerItems}
            value={ownerCharacterId}
            onValueChange={(value) => setOwnerCharacterId(value ?? "")}
          >
            <SelectTrigger id="propOwner" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {ownerItems.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </Field>
        <Field>
          <FieldLabel htmlFor="propDescription">{t("prop.description")}</FieldLabel>
          <Textarea
            id="propDescription"
            value={description}
            maxLength={4000}
            rows={4}
            placeholder={t("prop.descriptionPlaceholder")}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
      </FieldGroup>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" disabled={pending} onClick={onClose}>
          <X data-icon="inline-start" />
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={pending || !name.trim()}>
          {pending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : null}
          {t("common.save")}
        </Button>
      </div>
    </form>
  );
}

function PropCard({
  projectId,
  prop,
  onEdit,
  onDelete,
  onError,
}: {
  projectId: string;
  prop: Prop;
  onEdit: () => void;
  onDelete: () => void;
  onError: (message: string) => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [prompt, setPrompt] = useState(prop.finalPrompt);
  const draftController = useRef<AbortController | null>(null);
  const drawController = useRef<AbortController | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.props(projectId) });

  // Drafting returns the prompt for review; it only reaches the row when the user saves.
  const draftMutation = useMutation({
    mutationFn: () =>
      draftPropPromptAction(
        projectId,
        prop.id,
        { name: prop.name, description: prop.description },
        draftController.current?.signal
      ),
    onSuccess: (response) => setPrompt(response.prompt),
    onError: (error) => {
      if (isCancel(error)) return;
      onError(resolveRequestError(error, t("character.draftPromptFailed")));
    },
    onSettled: () => {
      draftController.current = null;
    },
  });

  const saveMutation = useMutation({
    mutationFn: () => updatePropAction(projectId, prop.id, { finalPrompt: prompt }),
    onSuccess: () => void refresh(),
    onError: (error) => onError(resolveRequestError(error, t("reference.saveFailed"))),
  });

  const drawMutation = useMutation({
    mutationFn: () =>
      generatePropImageAction(projectId, prop.id, { prompt: prompt.trim() }, drawController.current?.signal),
    onSuccess: () => void refresh(),
    onError: (error) => {
      if (isCancel(error)) return;
      onError(resolveRequestError(error, t("character.generateSheetFailed")));
    },
    onSettled: () => {
      drawController.current = null;
    },
  });

  const uploadMutation = useMutation({
    mutationFn: (imageData: string) => uploadPropImageAction(projectId, prop.id, { imageData }),
    onSuccess: () => void refresh(),
    onError: (error) => onError(resolveRequestError(error, t("reference.uploadFailed"))),
  });

  const busy = draftMutation.isPending || saveMutation.isPending || drawMutation.isPending || uploadMutation.isPending;

  return (
    <section className="grid gap-4 rounded-lg border border-border/70 bg-card/60 p-4 md:grid-cols-[minmax(0,1fr)_240px]">
      <div className="flex min-w-0 flex-col gap-3">
        <header className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="truncate text-sm font-semibold">{prop.name}</h2>
              {prop.ownerName ? (
                <Badge variant="outline" className="text-[10px]">
                  {prop.ownerName}
                </Badge>
              ) : null}
            </div>
            {prop.description ? (
              <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{prop.description}</p>
            ) : null}
          </div>
          <div className="flex gap-1">
            <Button variant="ghost" size="sm" onClick={onEdit}>
              <Pencil data-icon="inline-start" />
              {t("common.edit")}
            </Button>
            <Button variant="ghost" size="sm" onClick={onDelete}>
              <Trash2 data-icon="inline-start" />
              {t("common.delete")}
            </Button>
          </div>
        </header>

        <PromptField
          id={`propPrompt-${prop.id}`}
          label={t("prop.prompt")}
          kind="prop"
          presetKind="prop"
          value={prompt}
          onChange={setPrompt}
          placeholder={t("prop.promptPlaceholder")}
          busy={busy}
          onError={onError}
          actions={
            <DraftPromptButton
              drafting={draftMutation.isPending}
              disabled={busy}
              onStart={() => {
                draftController.current = new AbortController();
                draftMutation.mutate();
              }}
              onStop={() => {
                draftController.current?.abort();
                draftController.current = null;
                draftMutation.reset();
              }}
            />
          }
        />

        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" disabled={busy} onClick={() => saveMutation.mutate()}>
            {saveMutation.isPending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : null}
            {t("common.save")}
          </Button>
        </div>
      </div>

      <ReferenceImage
        url={prop.imageUrl}
        generateLabel={t("prop.generateImage")}
        generatingLabel={t("character.generatingSheet")}
        uploadLabel={t("prop.uploadImage")}
        busy={busy}
        generating={drawMutation.isPending}
        onGenerate={() => {
          drawController.current = new AbortController();
          drawMutation.mutate();
        }}
        onStop={() => {
          drawController.current?.abort();
          drawController.current = null;
          drawMutation.reset();
        }}
        onUpload={(dataUrl) => uploadMutation.mutate(dataUrl)}
        onError={onError}
      />
    </section>
  );
}

export default function PropsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Prop | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Prop | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const propsQuery = useQuery({
    queryKey: queryKeys.props(projectId),
    queryFn: () => listPropsAction(projectId),
  });
  // The cast, so a prop can name its owner. Fetched per route, not hoisted into the layout.
  const charactersQuery = useQuery({
    queryKey: queryKeys.characters(projectId),
    queryFn: () => listCharactersAction(projectId),
  });
  const projectsQuery = useQuery({
    queryKey: queryKeys.projects,
    queryFn: listProjectsAction,
    staleTime: 300_000,
  });
  const project = projectsQuery.data?.projects.find((item) => item.id === projectId);

  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.props(projectId) });

  const saveMutation = useMutation({
    mutationFn: (values: PropFormValues) =>
      editing ? updatePropAction(projectId, editing.id, values) : createPropAction(projectId, values),
    onSuccess: () => {
      setFormOpen(false);
      setMessage(null);
      void refresh();
    },
    onError: (error) => setMessage(resolveRequestError(error, t("reference.saveFailed"))),
  });

  const deleteMutation = useMutation({
    mutationFn: (propId: string) => deletePropAction(projectId, propId),
    onSuccess: () => {
      setPendingDelete(null);
      void refresh();
    },
    onError: (error) => setMessage(resolveRequestError(error, t("reference.deleteFailed"))),
  });

  const mergeMutation = useMutation({
    mutationFn: () => mergePropSheetAction(projectId),
    onSuccess: () => {
      setMessage(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("character.mergeFailed"))),
  });

  const props = propsQuery.data?.props ?? [];

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{t("prop.title")}</h1>
          <p className="mt-1 max-w-2xl text-xs text-muted-foreground">{t("prop.subtitle")}</p>
        </div>
        <Button
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
        >
          <Plus data-icon="inline-start" />
          {t("prop.newProp")}
        </Button>
      </div>

      <section className="grid gap-4 rounded-lg border border-border/70 bg-card/40 p-4 md:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("prop.propSheet")}</p>
          <SheetPreview url={project?.propSheetUrl ?? null} emptyLabel={t("prop.noPropSheet")} />
        </div>
        <div className="flex items-start">
          <MergeButton
            label={t("prop.mergeProps")}
            pendingLabel={t("character.merging")}
            pending={mergeMutation.isPending}
            disabled={props.length === 0}
            onClick={() => mergeMutation.mutate()}
          />
        </div>
      </section>

      {message ? <p className="text-sm text-amber-600">{message}</p> : null}

      {propsQuery.isLoading ? (
        <Skeleton className="h-40 rounded-lg" />
      ) : props.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/70 p-8 text-center text-sm text-muted-foreground">
          {t("prop.empty")}
        </p>
      ) : (
        props.map((prop) => (
          <PropCard
            // Keyed on updatedAt too, so a drawn image writing back finalPrompt re-seeds the
            // field instead of leaving the old text in place.
            key={`${prop.id}-${prop.updatedAt}`}
            projectId={projectId}
            prop={prop}
            onEdit={() => {
              setEditing(prop);
              setFormOpen(true);
            }}
            onDelete={() => setPendingDelete(prop)}
            onError={setMessage}
          />
        ))
      )}

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? t("prop.editProp") : t("prop.newProp")}</DialogTitle>
            <DialogDescription>{t("prop.subtitle")}</DialogDescription>
          </DialogHeader>
          {formOpen ? (
            <PropForm
              key={editing?.id ?? "new"}
              prop={editing}
              characters={charactersQuery.data?.characters ?? []}
              pending={saveMutation.isPending}
              onSubmit={(values) => saveMutation.mutate(values)}
              onClose={() => setFormOpen(false)}
            />
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(pendingDelete)} onOpenChange={(open) => (open ? null : setPendingDelete(null))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("prop.deleteProp")}</DialogTitle>
            <DialogDescription>
              {t("prop.deletePropConfirm", { name: pendingDelete?.name ?? "" })}
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button variant="outline" disabled={deleteMutation.isPending} onClick={() => setPendingDelete(null)}>
              <X data-icon="inline-start" />
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={deleteMutation.isPending}
              onClick={() => pendingDelete && deleteMutation.mutate(pendingDelete.id)}
            >
              {deleteMutation.isPending ? (
                <Loader2 data-icon="inline-start" className="animate-spin" />
              ) : (
                <Trash2 data-icon="inline-start" />
              )}
              {t("common.delete")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
