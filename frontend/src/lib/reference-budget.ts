/**
 * How a shot's provider reference slots are shared between the editors that spend them.
 *
 * A shot's prefix prompts and its own prompt draw on one pool: the backend resolves them as
 * a single deduplicated list and refuses a save that overruns the model's cap. So every
 * editor has to be offered what is genuinely still free rather than the full cap — four
 * independent editors each offering four images is a form that can only be filled in wrong.
 *
 * The asset, not the mention, is the unit. Naming one image in two editors spends one slot,
 * which is why a sibling's reference the caller also holds is not counted against it.
 */

import type { GenerationReferenceInput } from "@/types/project";

export type ReferenceMedia = "image" | "video" | "audio";

export const referenceKey = (item: GenerationReferenceInput) => `${item.kind}:${item.id}`;

export type MediaLimits = Partial<Record<ReferenceMedia, number>>;

/** Distinct assets in `references`, counted per media. Assets not in `mediaOf` are ignored. */
export function countByMedia(
  references: GenerationReferenceInput[],
  mediaOf: (key: string) => ReferenceMedia | undefined,
): Record<ReferenceMedia, number> {
  const counts: Record<ReferenceMedia, number> = { image: 0, video: 0, audio: 0 };
  const seen = new Set<string>();
  for (const reference of references) {
    const key = referenceKey(reference);
    if (seen.has(key)) continue;
    seen.add(key);
    const media = mediaOf(key);
    if (media) counts[media] += 1;
  }
  return counts;
}

/**
 * The per-media budget left for one editor, given what its siblings have already taken.
 *
 * `own` is excluded from the deduction: an asset the editor itself holds is a slot it is
 * already paying for, and deducting it would make its own selection look over budget.
 */
export function remainingBudget(
  own: GenerationReferenceInput[],
  siblings: GenerationReferenceInput[][],
  mediaOf: (key: string) => ReferenceMedia | undefined,
  limits: MediaLimits,
): MediaLimits {
  const ownKeys = new Set(own.map(referenceKey));
  const taken = countByMedia(
    siblings.flat().filter((reference) => !ownKeys.has(referenceKey(reference))),
    mediaOf,
  );
  return {
    image: Math.max(0, (limits.image ?? 0) - taken.image),
    video: Math.max(0, (limits.video ?? 0) - taken.video),
    audio: Math.max(0, (limits.audio ?? 0) - taken.audio),
  };
}
