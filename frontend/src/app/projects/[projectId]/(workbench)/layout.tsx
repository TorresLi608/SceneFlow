"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Boxes,
  Clapperboard,
  Film,
  Info,
  Mic,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { listProjectsAction } from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { PreferencesSwitcher } from "@/components/preferences-switcher";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

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
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      {/* 顶部工作台导航条 */}
      <header className="flex shrink-0 items-center justify-between border-b border-border/70 bg-card/50 px-4 py-3 backdrop-blur-xl md:px-6">
        <div className="flex items-center gap-3">
          <Link
            href="/ai-script"
            className="flex items-center gap-1.5 rounded-xl border border-border/70 bg-card/60 px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-all hover:bg-card hover:text-foreground cursor-pointer shadow-xs"
          >
            <ArrowLeft className="size-3.5" />
            {t("common.back")}
          </Link>
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-bold text-foreground">
              {project?.title ?? t("common.loading")}
            </span>
            {project?.status ? (
              <Badge variant="outline" className="text-[10px]">
                {project.status}
              </Badge>
            ) : null}
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <PreferencesSwitcher />
        </div>
      </header>

      {/* 主体工作台结构 */}
      <div className="flex min-h-0 flex-1 flex-col md:flex-row overflow-hidden">
        <nav
          aria-label={t("workbench.menu")}
          className="flex shrink-0 gap-1 overflow-x-auto border-b border-border/70 bg-card/30 p-3 backdrop-blur-md md:w-[230px] md:flex-col md:overflow-y-auto md:border-b-0 md:border-r md:p-4 chat-message-list-scrollbar"
        >
          <p className="hidden px-2 pb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground md:block">
            {t("workbench.menuHeading")}
          </p>
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
                  "group relative flex shrink-0 items-center gap-2.5 whitespace-nowrap rounded-xl px-3 py-2.5 text-xs font-semibold transition-all duration-150 cursor-pointer",
                  active
                    ? "bg-primary/10 text-primary shadow-xs dark:bg-primary/15"
                    : "text-muted-foreground hover:bg-muted/70 hover:text-foreground"
                )}
              >
                {active ? (
                  <span className="hidden md:block absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-primary" />
                ) : null}
                <Icon
                  className={cn(
                    "size-4 shrink-0 transition-colors",
                    active ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                  )}
                />
                <span>{section.label}</span>
              </Link>
            );
          })}
        </nav>

        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto p-4 md:p-6 chat-message-list-scrollbar">
          {children}
        </main>
      </div>
    </div>
  );
}
