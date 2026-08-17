"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Boxes, Clapperboard, Film, Info, Mic, Users } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { listProjectsAction } from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * The project workbench shell. Lives in a route group so it adds no path segment: the
 * sections below are `/projects/:id/info`, `/projects/:id/characters`, and so on.
 */
export default function ProjectWorkbenchLayout({ children }: { children: ReactNode }) {
  const { projectId } = useParams<{ projectId: string }>();
  const pathname = usePathname();
  const { t } = useI18n();

  const projectsQuery = useQuery({
    queryKey: queryKeys.projects,
    queryFn: listProjectsAction,
    staleTime: 300_000,
  });
  const project = projectsQuery.data?.projects.find((item) => item.id === projectId);

  const sections = [
    { key: "info", icon: Info, label: t("workbench.projectInfo") },
    { key: "characters", icon: Users, label: t("workbench.characters") },
    { key: "props", icon: Boxes, label: t("workbench.props") },
    { key: "voices", icon: Mic, label: t("workbench.voices") },
    { key: "episodes", icon: Clapperboard, label: t("workbench.episodes") },
    { key: "videos", icon: Film, label: t("workbench.videos") },
  ];

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="flex shrink-0 items-center gap-3 border-b border-border/70 px-4 py-3">
        <Link
          href="/ai-script"
          className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-muted/60"
        >
          <ArrowLeft className="size-4" />
          {t("common.back")}
        </Link>
        <span className="truncate text-sm font-semibold">{project?.title ?? t("common.loading")}</span>
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <nav
          aria-label={t("workbench.menu")}
          className="flex shrink-0 gap-1 overflow-x-auto border-b border-border/70 bg-card/50 p-3 md:w-[220px] md:flex-col md:overflow-visible md:border-b-0 md:border-r"
        >
          {sections.map((section) => {
            const href = `/projects/${projectId}/${section.key}`;
            const active = pathname === href || pathname.startsWith(`${href}/`);
            const Icon = section.icon;
            return (
              <Link
                key={section.key}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex shrink-0 items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-sm",
                  active ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60"
                )}
              >
                <Icon className="size-4" />
                {section.label}
              </Link>
            );
          })}
        </nav>

        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
