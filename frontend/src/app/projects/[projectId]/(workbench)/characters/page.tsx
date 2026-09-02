"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Pencil, Plus, Trash2, X } from "lucide-react";
import { useParams } from "next/navigation";
import { useRef, useState } from "react";

import { isCanceled } from "@/actions/job-actions";
import {
  createCharacterAction,
  createCharacterStateAction,
  deleteCharacterAction,
  deleteCharacterStateAction,
  draftCharacterStatePromptAction,
  generateCharacterStateImageAction,
  listCharactersAction,
  listProjectsAction,
  listVoicesAction,
  mergeCastSheetAction,
  mergeCharacterSheetAction,
  updateCharacterAction,
  updateCharacterStateAction,
  uploadCharacterStateImageAction,
} from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { DraftPromptButton, PromptField } from "@/components/prompt-field";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import type { Character, CharacterState, VoiceProfile } from "@/types/project";

import { MergeButton, SheetPreview } from "../_components/project-cover-field";
import { ReferenceImage } from "../_components/reference-image";

interface CharacterFormValues {
  name: string;
  aliases: string;
  description: string;
  appearancePrompt: string;
}

function CharacterForm({
  character,
  onSubmit,
  onClose,
  pending,
}: {
  character: Character | null;
  onSubmit: (values: CharacterFormValues) => void;
  onClose: () => void;
  pending: boolean;
}) {
  const { t } = useI18n();
  const [name, setName] = useState(character?.name ?? "");
  const [aliases, setAliases] = useState(character?.aliases ?? "");
  const [description, setDescription] = useState(character?.description ?? "");
  const [appearancePrompt, setAppearancePrompt] = useState(character?.appearancePrompt ?? "");

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({
          name: name.trim(),
          aliases: aliases.trim(),
          description: description.trim(),
          appearancePrompt: appearancePrompt.trim(),
        });
      }}
    >
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="characterName">{t("character.name")}</FieldLabel>
          <Input id="characterName" value={name} maxLength={80} required onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field>
          <FieldLabel htmlFor="characterAliases">{t("character.aliases")}</FieldLabel>
          <Input id="characterAliases" value={aliases} maxLength={400} onChange={(event) => setAliases(event.target.value)} />
        </Field>
        <Field>
          <FieldLabel htmlFor="characterDescription">{t("character.description")}</FieldLabel>
          <Textarea
            id="characterDescription"
            value={description}
            maxLength={4000}
            rows={3}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="characterAppearance">{t("character.appearancePrompt")}</FieldLabel>
          <Textarea
            id="characterAppearance"
            value={appearancePrompt}
            maxLength={4000}
            rows={3}
            onChange={(event) => setAppearancePrompt(event.target.value)}
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

function StateEditor({
  projectId,
  character,
  state,
  onError,
}: {
  projectId: string;
  character: Character;
  state: CharacterState;
  onError: (message: string) => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [name, setName] = useState(state.name);
  const [description, setDescription] = useState(state.description);
  const [prompt, setPrompt] = useState(state.finalPrompt);
  // Which built-in template the draft should be written against. Empty means the backend's
  // default (the turnaround sheet), which is exactly what a dropped selection looked like.
  const [preset, setPreset] = useState("");
  const [fromEpisode, setFromEpisode] = useState(state.fromEpisode?.toString() ?? "");
  const [toEpisode, setToEpisode] = useState(state.toEpisode?.toString() ?? "");
  const draftController = useRef<AbortController | null>(null);

  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.characters(projectId) });
  const episodeNumber = (value: string) => (value.trim() ? Number(value) : null);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateCharacterStateAction(projectId, character.id, state.id, {
        name: name.trim(),
        description: description.trim(),
        finalPrompt: prompt,
        fromEpisode: episodeNumber(fromEpisode),
        toEpisode: episodeNumber(toEpisode),
      }),
    onSuccess: () => void refresh(),
    onError: (error) => onError(resolveRequestError(error, t("reference.saveFailed"))),
  });

  // Drafting returns the prompt for review; it only reaches the row when the user saves.
  const draftMutation = useMutation({
    mutationFn: () =>
      draftCharacterStatePromptAction(
        projectId,
        character.id,
        state.id,
        { name: name.trim(), description: description.trim(), preset },
        draftController.current?.signal
      ),
    onSuccess: (response) => setPrompt(response.prompt),
    onError: (error) => {
      if (isCanceled(error)) return;
      onError(resolveRequestError(error, t("character.draftPromptFailed")));
    },
    onSettled: () => {
      draftController.current = null;
    },
  });

  const drawController = useRef<AbortController | null>(null);
  const drawMutation = useMutation({
    mutationFn: () =>
      generateCharacterStateImageAction(
        projectId,
        character.id,
        state.id,
        { prompt: prompt.trim() },
        drawController.current?.signal
      ),
    onSuccess: () => void refresh(),
    onError: (error) => {
      if (isCanceled(error)) return;
      onError(resolveRequestError(error, t("character.generateSheetFailed")));
    },
    onSettled: () => {
      drawController.current = null;
    },
  });

  const uploadMutation = useMutation({
    mutationFn: (imageData: string) =>
      uploadCharacterStateImageAction(projectId, character.id, state.id, { imageData }),
    onSuccess: () => void refresh(),
    onError: (error) => onError(resolveRequestError(error, t("reference.uploadFailed"))),
  });

  const removeMutation = useMutation({
    mutationFn: () => deleteCharacterStateAction(projectId, character.id, state.id),
    onSuccess: () => void refresh(),
    onError: (error) => onError(resolveRequestError(error, t("reference.deleteFailed"))),
  });

  const busy =
    saveMutation.isPending ||
    draftMutation.isPending ||
    drawMutation.isPending ||
    uploadMutation.isPending ||
    removeMutation.isPending;

  return (
    <div className="grid gap-4 rounded-lg border border-border/60 p-3 md:grid-cols-[minmax(0,1fr)_240px]">
      <div className="flex min-w-0 flex-col gap-3">
        <FieldGroup>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field>
              <FieldLabel htmlFor={`stateName-${state.id}`}>{t("character.stateName")}</FieldLabel>
              <Input
                id={`stateName-${state.id}`}
                value={name}
                maxLength={80}
                placeholder={t("character.stateNamePlaceholder")}
                onChange={(event) => setName(event.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor={`stateDescription-${state.id}`}>{t("character.stateDescription")}</FieldLabel>
              <Input
                id={`stateDescription-${state.id}`}
                value={description}
                maxLength={4000}
                placeholder={t("character.stateDescriptionPlaceholder")}
                onChange={(event) => setDescription(event.target.value)}
              />
            </Field>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field>
              <FieldLabel htmlFor={`stateFrom-${state.id}`}>{t("character.fromEpisode")}</FieldLabel>
              <Input
                id={`stateFrom-${state.id}`}
                type="number"
                min={1}
                value={fromEpisode}
                onChange={(event) => setFromEpisode(event.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor={`stateTo-${state.id}`}>{t("character.toEpisode")}</FieldLabel>
              <Input
                id={`stateTo-${state.id}`}
                type="number"
                min={1}
                value={toEpisode}
                onChange={(event) => setToEpisode(event.target.value)}
              />
            </Field>
          </div>
          <FieldDescription>{t("character.episodeRangeHint")}</FieldDescription>

          {/*
            One prompt field, not two. The built-in instruction template lives on the
            backend and is not editable — offering a copy of it beside this one only ever
            left users unsure which of the two actually drew the picture.
          */}
          <PromptField
            id={`statePrompt-${state.id}`}
            label={t("character.prompt")}
            kind="character"
            presetKind="character"
            preset={preset}
            onPresetChange={setPreset}
            value={prompt}
            onChange={setPrompt}
            placeholder={t("character.promptPlaceholder")}
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
        </FieldGroup>

        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" disabled={busy} onClick={() => saveMutation.mutate()}>
            {saveMutation.isPending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : null}
            {t("common.save")}
          </Button>
          <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={() => removeMutation.mutate()}>
            <Trash2 data-icon="inline-start" />
            {t("character.deleteState")}
          </Button>
        </div>
      </div>

      <ReferenceImage
        url={state.referenceImageUrl}
        generateLabel={t("character.generateSheet")}
        generatingLabel={t("character.generatingSheet")}
        uploadLabel={t("character.uploadSheet")}
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
    </div>
  );
}

function CharacterCard({
  projectId,
  character,
  voices,
  onEdit,
  onDelete,
  onError,
}: {
  projectId: string;
  character: Character;
  voices: VoiceProfile[];
  onEdit: () => void;
  onDelete: () => void;
  onError: (message: string) => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.characters(projectId) });

  const addStateMutation = useMutation({
    mutationFn: () => createCharacterStateAction(projectId, character.id, { name: t("character.newState") }),
    onSuccess: () => void refresh(),
    onError: (error) => onError(resolveRequestError(error, t("reference.saveFailed"))),
  });

  const mergeMutation = useMutation({
    mutationFn: () => mergeCharacterSheetAction(projectId, character.id),
    onSuccess: () => void refresh(),
    onError: (error) => onError(resolveRequestError(error, t("character.mergeFailed"))),
  });

  const bindMutation = useMutation({
    // "" unbinds; a JSON null would read as an absent field and keep the old profile.
    mutationFn: (voiceProfileId: string) =>
      updateCharacterAction(projectId, character.id, { voiceProfileId }),
    onSuccess: () => void refresh(),
    onError: (error) => onError(resolveRequestError(error, t("voice.bindFailed"))),
  });

  const voiceItems = [
    { value: "", label: t("voice.unbound") },
    ...voices.map((voice) => ({ value: voice.id, label: voice.name })),
  ];

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-border/70 bg-card/60 p-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold">{character.name}</h2>
          {character.description ? (
            <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{character.description}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <Select
            items={voiceItems}
            value={character.voiceProfileId ?? ""}
            onValueChange={(value) => bindMutation.mutate(value ?? "")}
          >
            <SelectTrigger className="w-40" aria-label={t("voice.bindLabel")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {voiceItems.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
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

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t("character.states")}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={addStateMutation.isPending}
              onClick={() => addStateMutation.mutate()}
            >
              <Plus data-icon="inline-start" />
              {t("character.newState")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={mergeMutation.isPending}
              onClick={() => mergeMutation.mutate()}
            >
              {mergeMutation.isPending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : null}
              {mergeMutation.isPending ? t("character.merging") : t("character.mergeCharacter")}
            </Button>
          </div>
        </div>

        {character.states.length === 0 ? (
          <p className="rounded-md border border-dashed border-border/70 p-4 text-center text-xs text-muted-foreground">
            {t("character.noStates")}
          </p>
        ) : (
          character.states.map((state) => (
            <StateEditor
              // Keyed on updatedAt too, so a server-side change (a drawn sheet writing back
              // finalPrompt) re-seeds the fields instead of leaving the old text in place.
              key={`${state.id}-${state.updatedAt}`}
              projectId={projectId}
              character={character}
              state={state}
              onError={onError}
            />
          ))
        )}

        {character.sheetImageUrl ? (
          <div className="max-w-sm">
            <SheetPreview url={character.sheetImageUrl} emptyLabel={t("character.noCastSheet")} />
          </div>
        ) : null}
      </div>
    </section>
  );
}

export default function CharactersPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Character | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Character | null>(null);
  const [message, setMessage] = useState<string | null>(null);

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
  const voicesQuery = useQuery({
    queryKey: queryKeys.voices(projectId),
    queryFn: () => listVoicesAction(projectId),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.characters(projectId) });

  const saveMutation = useMutation({
    mutationFn: (values: CharacterFormValues) =>
      editing
        ? updateCharacterAction(projectId, editing.id, values)
        : createCharacterAction(projectId, values),
    onSuccess: () => {
      setFormOpen(false);
      setMessage(null);
      void refresh();
    },
    onError: (error) => setMessage(resolveRequestError(error, t("reference.saveFailed"))),
  });

  const deleteMutation = useMutation({
    mutationFn: (characterId: string) => deleteCharacterAction(projectId, characterId),
    onSuccess: () => {
      setPendingDelete(null);
      void refresh();
    },
    onError: (error) => setMessage(resolveRequestError(error, t("reference.deleteFailed"))),
  });

  const mergeCastMutation = useMutation({
    mutationFn: () => mergeCastSheetAction(projectId),
    onSuccess: () => {
      setMessage(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("character.mergeFailed"))),
  });

  const characters = charactersQuery.data?.characters ?? [];

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{t("character.title")}</h1>
          <p className="mt-1 max-w-2xl text-xs text-muted-foreground">{t("character.subtitle")}</p>
        </div>
        <Button
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
        >
          <Plus data-icon="inline-start" />
          {t("character.newCharacter")}
        </Button>
      </div>

      <section className="grid gap-4 rounded-lg border border-border/70 bg-card/40 p-4 md:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t("character.castSheet")}
          </p>
          <SheetPreview url={project?.characterSheetUrl ?? null} emptyLabel={t("character.noCastSheet")} />
        </div>
        <div className="flex items-start">
          <MergeButton
            label={t("character.mergeCast")}
            pendingLabel={t("character.merging")}
            pending={mergeCastMutation.isPending}
            disabled={characters.length === 0}
            onClick={() => mergeCastMutation.mutate()}
          />
        </div>
      </section>

      {message ? <p className="text-sm text-amber-600">{message}</p> : null}

      {charactersQuery.isLoading ? (
        <Skeleton className="h-48 rounded-lg" />
      ) : characters.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/70 p-8 text-center text-sm text-muted-foreground">
          {t("character.empty")}
        </p>
      ) : (
        characters.map((character) => (
          <CharacterCard
            key={character.id}
            projectId={projectId}
            character={character}
            voices={voicesQuery.data?.voices ?? []}
            onEdit={() => {
              setEditing(character);
              setFormOpen(true);
            }}
            onDelete={() => setPendingDelete(character)}
            onError={setMessage}
          />
        ))
      )}

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? t("character.editCharacter") : t("character.newCharacter")}</DialogTitle>
            <DialogDescription>{t("character.subtitle")}</DialogDescription>
          </DialogHeader>
          {formOpen ? (
            <CharacterForm
              key={editing?.id ?? "new"}
              character={editing}
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
            <DialogTitle>{t("character.deleteCharacter")}</DialogTitle>
            <DialogDescription>
              {t("character.deleteCharacterConfirm", { name: pendingDelete?.name ?? "" })}
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
