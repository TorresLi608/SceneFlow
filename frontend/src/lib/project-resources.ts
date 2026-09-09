import type { GenerationReferenceInput, ProjectResource } from "../types/project";

export interface ReferenceAssetOption extends GenerationReferenceInput {
  label: string;
  media: "image" | "video" | "audio";
  url: string;
  description?: string;
  aliases?: string[];
  episodeId?: string | null;
  episodeNumber?: number | null;
  episodeTitle?: string;
  sceneOrder?: number | null;
}

export function matchesResource(asset: ReferenceAssetOption, search: string) {
  const text = [asset.label, asset.description, asset.episodeTitle, ...(asset.aliases ?? [])].join(" ").toLocaleLowerCase();
  return search.trim().toLocaleLowerCase().split(/\s+/).every((word) => text.includes(word));
}

export function localizeResource(resource: ProjectResource, locale: string): ProjectResource {
  // Canonical episode labels and their English counterparts are also accepted by the compiler.
  return { ...resource, label: locale === "en" && resource.episodeId ? resource.aliases[1] ?? resource.label : resource.label };
}
