"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Boxes,
  Clapperboard,
  Film,
  Info,
  Library,
  Mic,
  PanelLeftClose,
  PanelLeftOpen,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { listProjectsAction } from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { PreferencesSwitcher } from "@/components/preferences-switcher";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { usePreferencesStore } from "@/store/preferences-store";

export default function ProjectWorkbenchLayout({ children }: { children: ReactNode }) {
  const { projectId } = useParams<{ projectId: string }>();
  const pathname = usePathname();
  const { t } = useI18n();
  const collapsed = usePreferencesStore((state) => state.workbenchSidebarCollapsed);
  const toggleCollapsed = usePreferencesStore((state) => state.toggleWorkbenchSidebarCollapsed);

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
    { key: "assets", icon: Library, label: t("episode.assetLibrary") },
    { key: "episodes", icon: Clapperboard, label: t("workbench.episodes") },
    { key: "videos", icon: Film, label: t("workbench.videos") },
  ];

  return (
    <div className="safe-area flex h-dvh flex-col overflow-hidden bg-background">
      {/* 顶部工作台导航条 */}
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-border/70 bg-card/50 px-3 py-2 backdrop-blur-xl sm:px-4 sm:py-3 md:px-6">
        <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3">
          <Link
            href="/ai-script"
            className="flex shrink-0 items-center gap-1.5 rounded-xl border border-border/70 bg-card/60 px-2.5 py-2 text-xs font-medium text-muted-foreground transition-all hover:bg-card hover:text-foreground cursor-pointer shadow-xs"
          >
            <ArrowLeft className="size-3.5" />
            {t("common.back")}
          </Link>
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-sm font-bold text-foreground">
              {project?.title ?? t("common.loading")}
            </span>
            {project?.status ? (
              <Badge variant="outline" className="hidden shrink-0 text-[10px] sm:inline-flex">
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
          className={cn(
            "flex min-w-0 shrink-0 gap-1 overflow-x-auto overscroll-x-contain border-b border-border/70 bg-card/30 p-2 backdrop-blur-md md:flex-col md:overflow-y-auto md:border-b-0 md:border-r md:p-3 transition-[width] duration-300 ease-in-out chat-message-list-scrollbar",
            collapsed ? "md:w-[68px]" : "md:w-[230px]"
          )}
        >
          {!collapsed ? (
            <div className="hidden items-center justify-between px-2 pb-2 md:flex">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                {t("workbench.menuHeading")}
              </p>
              <Button
                variant="ghost"
                size="icon"
                onClick={toggleCollapsed}
                className="size-6 text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer"
                aria-label={t("home.collapseSidebar")}
                title={t("home.collapseSidebar")}
              >
                <PanelLeftClose className="size-3.5" />
              </Button>
            </div>
          ) : (
            <div className="hidden justify-center pb-2 md:flex">
              <Tooltip>
                <TooltipTrigger
                  render={<Button
                    variant="ghost"
                    size="icon"
                    onClick={toggleCollapsed}
                    className="size-8 rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer"
                    aria-label={t("home.expandSidebar")}
                  />}
                >
                  <PanelLeftOpen className="size-4" />
                </TooltipTrigger>
                <TooltipContent side="right" sideOffset={12}>
                  <span>{t("home.expandSidebar")}</span>
                </TooltipContent>
              </Tooltip>
            </div>
          )}

          {sections.map((section) => {
            const href = `/projects/${projectId}/${section.key}`;
            const active = pathname === href || pathname.startsWith(`${href}/`);
            const Icon = section.icon;

            const link = (
              <Link
                key={section.key}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "group relative flex shrink-0 items-center rounded-xl text-xs font-semibold transition-all duration-150 cursor-pointer",
                  collapsed
                    ? "gap-2.5 whitespace-nowrap px-3 py-2.5 md:mx-auto md:size-10 md:justify-center md:gap-0"
                    : "gap-2.5 whitespace-nowrap px-3 py-2.5",
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
                <span className={cn(collapsed && "md:sr-only")}>{section.label}</span>
              </Link>
            );

            if (collapsed) {
              return (
                <div key={section.key} className="shrink-0">
                  <div className="md:hidden">{link}</div>
                  <div className="hidden md:block">
                    <Tooltip>
                      <TooltipTrigger render={link} />
                      <TooltipContent side="right" sideOffset={12}>
                        <span>{section.label}</span>
                      </TooltipContent>
                    </Tooltip>
                  </div>
                </div>
              );
            }

            return link;
          })}
        </nav>

        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto p-4 md:p-6 chat-message-list-scrollbar">
          {children}
        </main>
      </div>
    </div>
  );
}
