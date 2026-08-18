"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Save } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";

import { listProjectsAction, updateProjectAction } from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import type { Project } from "@/types/project";

import { ProjectCoverField } from "../_components/project-cover-field";

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
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
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
