"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Pencil, Play, Plus, Trash2, X } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";

import {
  createVoiceAction,
  deleteVoiceAction,
  listProjectsAction,
  listVoicesAction,
  mergeVoiceSheetAction,
  previewVoiceAction,
  updateVoiceAction,
} from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import type { VoiceProfile } from "@/types/project";

import { MergeButton } from "../_components/project-cover-field";

interface VoiceFormValues {
  name: string;
  note: string;
  voiceProvider: string;
  voiceModel: string;
  sampleText: string;
}

function VoiceForm({
  voice,
  pending,
  onSubmit,
  onClose,
}: {
  voice: VoiceProfile | null;
  pending: boolean;
  onSubmit: (values: VoiceFormValues) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState(voice?.name ?? "");
  const [note, setNote] = useState(voice?.note ?? "");
  const [voiceProvider, setVoiceProvider] = useState(voice?.voiceProvider ?? "");
  const [voiceModel, setVoiceModel] = useState(voice?.voiceModel ?? "");
  const [sampleText, setSampleText] = useState(voice?.sampleText ?? "");

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({
          name: name.trim(),
          note: note.trim(),
          voiceProvider: voiceProvider.trim(),
          voiceModel: voiceModel.trim(),
          sampleText: sampleText.trim(),
        });
      }}
    >
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="voiceName">{t("voice.name")}</FieldLabel>
          <Input
            id="voiceName"
            value={name}
            maxLength={80}
            required
            placeholder={t("voice.namePlaceholder")}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="voiceNote">{t("voice.note")}</FieldLabel>
          <Input
            id="voiceNote"
            value={note}
            maxLength={4000}
            placeholder={t("voice.notePlaceholder")}
            onChange={(event) => setNote(event.target.value)}
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field>
            <FieldLabel htmlFor="voiceProvider">{t("voice.provider")}</FieldLabel>
            <Input
              id="voiceProvider"
              value={voiceProvider}
              maxLength={40}
              placeholder={t("voice.providerPlaceholder")}
              onChange={(event) => setVoiceProvider(event.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="voiceModel">{t("voice.model")}</FieldLabel>
            <Input
              id="voiceModel"
              value={voiceModel}
              maxLength={160}
              placeholder={t("voice.modelPlaceholder")}
              onChange={(event) => setVoiceModel(event.target.value)}
            />
          </Field>
        </div>
        <Field>
          <FieldLabel htmlFor="voiceSample">{t("voice.sampleText")}</FieldLabel>
          <Textarea
            id="voiceSample"
            value={sampleText}
            maxLength={1000}
            rows={3}
            onChange={(event) => setSampleText(event.target.value)}
          />
          <FieldDescription>{t("voice.sampleTextHint")}</FieldDescription>
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

export default function VoicesPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<VoiceProfile | null>(null);
  const [pendingDelete, setPendingDelete] = useState<VoiceProfile | null>(null);
  const [previewingId, setPreviewingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const voicesQuery = useQuery({
    queryKey: queryKeys.voices(projectId),
    queryFn: () => listVoicesAction(projectId),
  });
  const projectsQuery = useQuery({
    queryKey: queryKeys.projects,
    queryFn: listProjectsAction,
    staleTime: 300_000,
  });
  const project = projectsQuery.data?.projects.find((item) => item.id === projectId);

  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.voices(projectId) });

  const saveMutation = useMutation({
    mutationFn: (values: VoiceFormValues) =>
      editing ? updateVoiceAction(projectId, editing.id, values) : createVoiceAction(projectId, values),
    onSuccess: () => {
      setFormOpen(false);
      setMessage(null);
      void refresh();
    },
    onError: (error) => setMessage(resolveRequestError(error, t("reference.saveFailed"))),
  });

  const deleteMutation = useMutation({
    mutationFn: (voiceId: string) => deleteVoiceAction(projectId, voiceId),
    onSuccess: () => {
      setPendingDelete(null);
      void refresh();
      // A deleted profile releases the characters bound to it, so their cards are stale.
      void queryClient.invalidateQueries({ queryKey: queryKeys.characters(projectId) });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("reference.deleteFailed"))),
  });

  const previewMutation = useMutation({
    mutationFn: (voiceId: string) => previewVoiceAction(projectId, voiceId),
    onSuccess: () => {
      setMessage(null);
      void refresh();
    },
    onError: (error) => setMessage(resolveRequestError(error, t("voice.previewFailed"))),
    onSettled: () => setPreviewingId(null),
  });

  const mergeMutation = useMutation({
    mutationFn: () => mergeVoiceSheetAction(projectId),
    onSuccess: () => {
      setMessage(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("character.mergeFailed"))),
  });

  const voices = voicesQuery.data?.voices ?? [];

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{t("voice.title")}</h1>
          <p className="mt-1 max-w-2xl text-xs text-muted-foreground">{t("voice.subtitle")}</p>
        </div>
        <Button
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
        >
          <Plus data-icon="inline-start" />
          {t("voice.newVoice")}
        </Button>
      </div>

      <section className="flex flex-col gap-3 rounded-lg border border-border/70 bg-card/40 p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("voice.voiceSheet")}</p>
        {project?.voiceSheetUrl ? (
          <audio controls src={project.voiceSheetUrl} className="w-full max-w-md" />
        ) : (
          <p className="text-xs text-muted-foreground">{t("voice.noVoiceSheet")}</p>
        )}
        <div>
          <MergeButton
            label={t("voice.mergeSheet")}
            pendingLabel={t("character.merging")}
            pending={mergeMutation.isPending}
            disabled={voices.every((voice) => !voice.audioUrl)}
            onClick={() => mergeMutation.mutate()}
          />
        </div>
      </section>

      {message ? <p className="text-sm text-amber-600">{message}</p> : null}

      {voicesQuery.isLoading ? (
        <Skeleton className="h-40 rounded-lg" />
      ) : voices.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/70 p-8 text-center text-sm text-muted-foreground">
          {t("voice.empty")}
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {voices.map((voice) => (
            <section
              key={voice.id}
              className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-border/70 bg-card/60 p-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-2">
                  <h2 className="text-sm font-semibold">{voice.name}</h2>
                  {voice.voiceModel ? (
                    <span className="text-xs text-muted-foreground">{voice.voiceModel}</span>
                  ) : null}
                </div>
                {voice.note ? <p className="mt-1 text-xs text-muted-foreground">{voice.note}</p> : null}
                <p className="mt-2 text-xs leading-5">{voice.sampleText}</p>
                {voice.audioUrl ? (
                  <audio controls src={voice.audioUrl} className="mt-2 w-full max-w-sm" />
                ) : null}
              </div>
              <div className="flex flex-wrap gap-1">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={previewMutation.isPending}
                  onClick={() => {
                    setPreviewingId(voice.id);
                    previewMutation.mutate(voice.id);
                  }}
                >
                  {previewingId === voice.id ? (
                    <Loader2 data-icon="inline-start" className="animate-spin" />
                  ) : (
                    <Play data-icon="inline-start" />
                  )}
                  {previewingId === voice.id ? t("voice.previewing") : t("voice.preview")}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setEditing(voice);
                    setFormOpen(true);
                  }}
                >
                  <Pencil data-icon="inline-start" />
                  {t("common.edit")}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setPendingDelete(voice)}>
                  <Trash2 data-icon="inline-start" />
                  {t("common.delete")}
                </Button>
              </div>
            </section>
          ))}
        </div>
      )}

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? t("voice.editVoice") : t("voice.newVoice")}</DialogTitle>
            <DialogDescription>{t("voice.subtitle")}</DialogDescription>
          </DialogHeader>
          {formOpen ? (
            <VoiceForm
              key={editing?.id ?? "new"}
              voice={editing}
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
            <DialogTitle>{t("voice.deleteVoice")}</DialogTitle>
            <DialogDescription>
              {t("voice.deleteVoiceConfirm", { name: pendingDelete?.name ?? "" })}
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
