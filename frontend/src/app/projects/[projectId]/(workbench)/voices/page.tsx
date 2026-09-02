"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AudioLines, Download, Loader2, Pencil, Play, Sparkles, Square, Trash2, Volume2, X } from "lucide-react";
import { useParams } from "next/navigation";
import { useRef, useState } from "react";

import { isCanceled } from "@/actions/job-actions";
import {
  designVoiceProfileAction,
  deleteVoiceAction,
  importVoiceProfileAction,
  listProjectsAction,
  listVoicesAction,
  mergeVoiceSheetAction,
  previewVoiceAction,
  updateVoiceAction,
} from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { listUserVoicesAction } from "@/actions/voice-generation-actions";
import { PromptField } from "@/components/prompt-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { artifactBffUrl } from "@/lib/artifact-url";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { VoiceProfile } from "@/types/project";

/**
 * Designing a voice for this series, mirroring the standalone voice workspace: name it,
 * describe the timbre, audition it, keep it.
 *
 * The provider and model are not asked for. They come from the project's audio
 * configuration, because they are an account credential detail — the old form let a user
 * type a model name by hand, which is how a series ended up with voice profiles no
 * synthesiser here could actually voice.
 */
function DesignVoiceCard({ projectId, onError }: { projectId: string; onError: (message: string) => void }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [voicePrompt, setVoicePrompt] = useState("");
  const [previewText, setPreviewText] = useState("");
  const [sampleText, setSampleText] = useState("");
  const controller = useRef<AbortController | null>(null);

  const designMutation = useMutation({
    mutationFn: () =>
      designVoiceProfileAction(
        projectId,
        {
          name: name.trim(),
          voicePrompt: voicePrompt.trim(),
          previewText: previewText.trim(),
          sampleText: sampleText.trim(),
        },
        controller.current?.signal
      ),
    onSuccess: () => {
      setName("");
      setVoicePrompt("");
      setPreviewText("");
      setSampleText("");
      void queryClient.invalidateQueries({ queryKey: queryKeys.voices(projectId) });
    },
    onError: (error) => {
      if (isCanceled(error)) return;
      onError(resolveRequestError(error, t("voice.designFailed")));
    },
    onSettled: () => {
      controller.current = null;
    },
  });

  const designing = designMutation.isPending;
  const canDesign = Boolean(name.trim() && voicePrompt.trim() && previewText.trim());

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-border/70 bg-card/60 p-4">
      <div>
        <h2 className="text-sm font-semibold">{t("voice.designSection")}</h2>
        <p className="mt-1 text-xs text-muted-foreground">{t("voice.designSectionHint")}</p>
      </div>

      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="designVoiceName">{t("voice.name")}</FieldLabel>
          <Input
            id="designVoiceName"
            value={name}
            maxLength={80}
            placeholder={t("voice.namePlaceholder")}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>

        <PromptField
          id="designVoicePrompt"
          label={t("voice.prompt")}
          kind="voice"
          value={voicePrompt}
          onChange={setVoicePrompt}
          placeholder={t("voice.promptPlaceholder")}
          busy={designing}
          onError={onError}
          maxLength={1000}
        />

        <Field>
          <FieldLabel htmlFor="designVoicePreview">{t("voice.previewText")}</FieldLabel>
          <Textarea
            id="designVoicePreview"
            value={previewText}
            maxLength={1000}
            rows={3}
            placeholder={t("voice.previewTextPlaceholder")}
            onChange={(event) => setPreviewText(event.target.value)}
          />
        </Field>

        <Field>
          <FieldLabel htmlFor="designVoiceSample">{t("voice.sampleTextLabel")}</FieldLabel>
          <Textarea
            id="designVoiceSample"
            value={sampleText}
            maxLength={1000}
            rows={2}
            onChange={(event) => setSampleText(event.target.value)}
          />
          <FieldDescription>{t("voice.sampleTextHint")}</FieldDescription>
        </Field>
      </FieldGroup>

      <div>
        <Button
          type="button"
          variant={designing ? "destructive" : "default"}
          // Stopping stays available while it runs; only starting needs the three fields.
          disabled={designing ? false : !canDesign}
          onClick={() => {
            if (designing) {
              controller.current?.abort();
              controller.current = null;
              designMutation.reset();
              return;
            }
            controller.current = new AbortController();
            designMutation.mutate();
          }}
          className={cn("cursor-pointer transition-colors", designing && "animate-pulse font-medium")}
        >
          {designing ? (
            <Square data-icon="inline-start" className="size-3 fill-current" />
          ) : (
            <Sparkles data-icon="inline-start" />
          )}
          {designing ? t("common.stopGeneration") : t("voice.generatePreview")}
        </Button>
      </div>

      {designing ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <AudioLines className="size-4 animate-pulse text-primary" />
          {t("voice.generating")}
        </div>
      ) : null}
    </section>
  );
}

/** Reuse a timbre already on the account rather than paying to design the same voice twice. */
function ImportVoiceCard({ projectId, onError }: { projectId: string; onError: (message: string) => void }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState("");

  const libraryQuery = useQuery({
    queryKey: queryKeys.userVoices,
    queryFn: listUserVoicesAction,
  });
  const library = libraryQuery.data?.voices ?? [];
  const effective = library.some((item) => item.id === selected) ? selected : (library[0]?.id ?? "");

  const importMutation = useMutation({
    mutationFn: () => importVoiceProfileAction(projectId, { userVoiceId: effective }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.voices(projectId) }),
    onError: (error) => onError(resolveRequestError(error, t("voice.importFailed"))),
  });

  const items = library.map((voice) => ({ value: voice.id, label: voice.name || voice.voiceId }));

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-border/70 bg-card/40 p-4">
      <div>
        <h2 className="text-sm font-semibold">{t("voice.importSection")}</h2>
        <p className="mt-1 text-xs text-muted-foreground">{t("voice.importSectionHint")}</p>
      </div>

      {libraryQuery.isLoading ? (
        <Skeleton className="h-10 rounded-lg" />
      ) : library.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t("voice.importEmpty")}</p>
      ) : (
        <div className="flex flex-wrap items-end gap-3">
          <Select items={items} value={effective} onValueChange={(value) => setSelected(value ?? "")}>
            <SelectTrigger className="w-full max-w-sm" aria-label={t("voice.importSection")}>
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
          <Button
            type="button"
            variant="outline"
            disabled={!effective || importMutation.isPending}
            onClick={() => importMutation.mutate()}
          >
            {importMutation.isPending ? (
              <Loader2 data-icon="inline-start" className="animate-spin" />
            ) : (
              <Download data-icon="inline-start" />
            )}
            {t("voice.import")}
          </Button>
        </div>
      )}
    </section>
  );
}

interface VoiceEditValues {
  name: string;
  note: string;
  sampleText: string;
}

/** Only the fields a user still authors by hand. Provider and model are set by design/import. */
function EditVoiceForm({
  voice,
  pending,
  onSubmit,
  onClose,
}: {
  voice: VoiceProfile;
  pending: boolean;
  onSubmit: (values: VoiceEditValues) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState(voice.name);
  const [note, setNote] = useState(voice.note);
  const [sampleText, setSampleText] = useState(voice.sampleText);

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({ name: name.trim(), note: note.trim(), sampleText: sampleText.trim() });
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
        <Field>
          <FieldLabel htmlFor="voiceSample">{t("voice.sampleTextLabel")}</FieldLabel>
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
    mutationFn: (values: VoiceEditValues) => updateVoiceAction(projectId, editing!.id, values),
    onSuccess: () => {
      setEditing(null);
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
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{t("voice.title")}</h1>
        <p className="mt-1 max-w-2xl text-xs text-muted-foreground">{t("voice.subtitle")}</p>
      </div>

      {message ? <p className="text-sm text-amber-600">{message}</p> : null}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,360px)]">
        <DesignVoiceCard projectId={projectId} onError={setMessage} />
        <div className="flex flex-col gap-4">
          <ImportVoiceCard projectId={projectId} onError={setMessage} />

          <section className="flex flex-col gap-3 rounded-lg border border-border/70 bg-card/40 p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("voice.voiceSheet")}</p>
            {project?.voiceSheetUrl ? (
              <audio controls src={project.voiceSheetUrl} className="w-full" />
            ) : (
              <p className="text-xs text-muted-foreground">{t("voice.noVoiceSheet")}</p>
            )}
            <div>
              <Button
                type="button"
                disabled={mergeMutation.isPending || voices.every((voice) => !voice.audioUrl)}
                onClick={() => mergeMutation.mutate()}
              >
                {mergeMutation.isPending ? (
                  <Loader2 data-icon="inline-start" className="animate-spin" />
                ) : (
                  <Sparkles data-icon="inline-start" />
                )}
                {mergeMutation.isPending ? t("character.merging") : t("voice.mergeSheet")}
              </Button>
            </div>
          </section>
        </div>
      </div>

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
                <div className="flex flex-wrap items-center gap-2">
                  <span className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Volume2 className="size-3.5" />
                  </span>
                  <h2 className="text-sm font-semibold">{voice.name}</h2>
                  {voice.voiceModel ? (
                    <Badge variant="outline" className="text-[10px]">
                      {voice.voiceModel}
                    </Badge>
                  ) : null}
                </div>
                {voice.note ? <p className="mt-1 text-xs text-muted-foreground">{voice.note}</p> : null}
                <p className="mt-2 text-xs leading-5">{voice.sampleText}</p>
                {voice.audioUrl ? (
                  <audio controls src={artifactBffUrl(voice.audioUrl)} className="mt-2 w-full max-w-sm" />
                ) : null}
              </div>
              <div className="flex flex-wrap gap-1">
                {!voice.audioUrl ? (
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
                ) : null}
                <Button variant="ghost" size="sm" onClick={() => setEditing(voice)}>
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

      <Dialog open={Boolean(editing)} onOpenChange={(open) => (open ? null : setEditing(null))}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("voice.editVoice")}</DialogTitle>
            <DialogDescription>{t("voice.subtitle")}</DialogDescription>
          </DialogHeader>
          {editing ? (
            <EditVoiceForm
              key={editing.id}
              voice={editing}
              pending={saveMutation.isPending}
              onSubmit={(values) => saveMutation.mutate(values)}
              onClose={() => setEditing(null)}
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
