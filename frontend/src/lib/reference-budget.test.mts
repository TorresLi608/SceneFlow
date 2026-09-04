import assert from "node:assert/strict";
import { test } from "node:test";

// @ts-expect-error Node's type stripping executes this TypeScript source directly.
import { countByMedia, remainingBudget, type ReferenceMedia } from "./reference-budget.ts";
import type { GenerationReferenceInput } from "../types/project";

const ref = (kind: string, id: string) => ({ kind, id }) as GenerationReferenceInput;

/** A tiny asset catalogue: the editor resolves an asset's media the same way. */
const MEDIA: Record<string, ReferenceMedia> = {
  "character:c1": "image",
  "character:c2": "image",
  "tone:e1": "image",
  "sceneVideo:s1": "video",
  "voice:v1": "audio",
};
const mediaOf = (key: string) => MEDIA[key];

test("an asset named twice counts once", () => {
  const counts = countByMedia([ref("character", "c1"), ref("character", "c1")], mediaOf);
  assert.equal(counts.image, 1);
});

test("unknown assets are ignored rather than counted as images", () => {
  // A reference whose asset has been deleted must not eat a slot the user cannot see.
  assert.deepEqual(countByMedia([ref("prop", "gone")], mediaOf), { image: 0, video: 0, audio: 0 });
});

test("each media kind has its own budget", () => {
  const counts = countByMedia(
    [ref("character", "c1"), ref("sceneVideo", "s1"), ref("voice", "v1")],
    mediaOf,
  );
  assert.deepEqual(counts, { image: 1, video: 1, audio: 1 });
});

test("a sibling's references are deducted from what is left", () => {
  const budget = remainingBudget([], [[ref("tone", "e1")], [ref("character", "c1")]], mediaOf, {
    image: 4,
  });
  assert.equal(budget.image, 2);
});

test("an asset the editor already holds is not deducted from itself", () => {
  // Otherwise a shared mention makes the editor's own selection look over budget and the
  // picker refuses to show the asset the user has already picked.
  const own = [ref("tone", "e1")];
  const budget = remainingBudget(own, [[ref("tone", "e1")], [ref("character", "c1")]], mediaOf, {
    image: 4,
  });
  assert.equal(budget.image, 3);
});

test("the budget never goes negative", () => {
  const budget = remainingBudget(
    [],
    [[ref("character", "c1"), ref("character", "c2"), ref("tone", "e1")]],
    mediaOf,
    { image: 2 },
  );
  assert.equal(budget.image, 0);
});

test("a model that takes no references of a kind offers none", () => {
  const budget = remainingBudget([], [], mediaOf, { image: 4 });
  assert.deepEqual(budget, { image: 4, video: 0, audio: 0 });
});
