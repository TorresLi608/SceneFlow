"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Pencil, Plus, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { createEpisodeAction, deleteEpisodeAction, listEpisodesAction } from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import type { EpisodeSummary } from "@/types/project";

interface EpisodeFormValues {
  title: string;
  synopsis: string;
}

/**
 * Creating an episode asks for exactly two things. Editing them lives in the episode editor
 * alongside the script they describe — a dialog out here could only ever show the title and
 * synopsis in isolation, which is where they make the least sense.
 */
function NewEpisodeForm({
  pending,
  onSubmit,
  onClose,
}: {
  pending: boolean;
  onSubmit: (values: EpisodeFormValues) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [title, setTitle] = useState("");
  const [synopsis, setSynopsis] = useState("");

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({ title: title.trim(), synopsis: synopsis.trim() });
      }}
    >
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="episodeTitle">{t("episode.name")}</FieldLabel>
          <Input
            id="episodeTitle"
            value={title}
            maxLength={80}
            required
            placeholder={t("episode.namePlaceholder")}
            onChange={(event) => setTitle(event.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="episodeSynopsis">{t("episode.synopsis")}</FieldLabel>
          <Textarea
            id="episodeSynopsis"
            value={synopsis}
            maxLength={4000}
            rows={3}
            placeholder={t("episode.synopsisPlaceholder")}
            onChange={(event) => setSynopsis(event.target.value)}
          />
        </Field>
      </FieldGroup>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" disabled={pending} onClick={onClose}>
          <X data-icon="inline-start" />
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={pending || !title.trim()}>
          {pending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : null}
          {t("common.save")}
        </Button>
      </div>
    </form>
  );
}

export default function EpisodesPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { t, formatDateTime } = useI18n();
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<EpisodeSummary | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const episodesQuery = useQuery({
    queryKey: queryKeys.episodes(projectId),
    queryFn: () => listEpisodesAction(projectId),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.episodes(projectId) });

  const createMutation = useMutation({
    mutationFn: (values: EpisodeFormValues) => createEpisodeAction(projectId, values),
    onSuccess: () => {
      setFormOpen(false);
      setMessage(null);
      void refresh();
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("episode.saveFailed"))),
  });

  const deleteMutation = useMutation({
    mutationFn: (episodeId: string) => deleteEpisodeAction(projectId, episodeId),
    onSuccess: () => {
      setPendingDelete(null);
      void refresh();
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("reference.deleteFailed"))),
  });

  const episodes = episodesQuery.data?.episodes ?? [];
  const toneLabel = (episode: EpisodeSummary) =>
    episode.toneImageStatus === "success"
      ? t("episode.toneReady")
      : episode.toneImageStatus === "error"
        ? t("episode.toneFailed")
        : t("episode.toneMissing");

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{t("episode.title")}</h1>
          <p className="mt-1 max-w-2xl text-xs text-muted-foreground">{t("episode.subtitle")}</p>
        </div>
        <Button onClick={() => setFormOpen(true)}>
          <Plus data-icon="inline-start" />
          {t("episode.newEpisode")}
        </Button>
      </div>

      {message ? <p className="text-sm text-amber-600">{message}</p> : null}

      {episodesQuery.isLoading ? (
        <Skeleton className="h-40 rounded-lg" />
      ) : episodes.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/70 p-8 text-center text-sm text-muted-foreground">
          {t("episode.empty")}
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {episodes.map((episode) => (
            <section
              key={episode.id}
              className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-border/70 bg-card/60 p-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-sm font-semibold">{episode.title}</h2>
                  <Badge variant="outline">{t("episode.shotCount", { count: episode.sceneCount })}</Badge>
                  <Badge variant={episode.toneImageStatus === "success" ? "default" : "outline"}>
                    {toneLabel(episode)}
                  </Badge>
                </div>
                {episode.synopsis ? (
                  <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{episode.synopsis}</p>
                ) : null}
                <p className="mt-1 text-xs text-muted-foreground">{formatDateTime(episode.updatedAt)}</p>
              </div>
              <div className="flex flex-wrap gap-1">
                <Button size="sm" render={<Link href={`/projects/${projectId}/episode/${episode.id}`} />}>
                  <Pencil data-icon="inline-start" />
                  {t("episode.edit")}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setPendingDelete(episode)}>
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
            <DialogTitle>{t("episode.newEpisode")}</DialogTitle>
            <DialogDescription>{t("episode.subtitle")}</DialogDescription>
          </DialogHeader>
          {/* Mounted only while open, so a cancelled draft does not survive into the next one. */}
          {formOpen ? (
            <NewEpisodeForm
              pending={createMutation.isPending}
              onSubmit={(values) => createMutation.mutate(values)}
              onClose={() => setFormOpen(false)}
            />
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(pendingDelete)} onOpenChange={(open) => (open ? null : setPendingDelete(null))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("episode.deleteEpisode")}</DialogTitle>
            <DialogDescription>
              {t("episode.deleteEpisodeConfirm", { title: pendingDelete?.title ?? "" })}
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
