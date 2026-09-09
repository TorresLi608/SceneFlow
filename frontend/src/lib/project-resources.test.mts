import assert from "node:assert/strict";
import { test } from "node:test";
// @ts-expect-error Node runs the TypeScript module directly.
import { matchesResource, localizeResource } from "./project-resources.ts";
import type { ProjectResource } from "../types/project";

test("resources search across episode, shot, description and bilingual aliases", () => {
  const resource: ProjectResource = {
    kind: "sceneImage", id: "shot-two", label: "第2集 · 分镜1 · 图片", media: "image", url: "/image",
    episodeId: "two", episodeNumber: 2, episodeTitle: "山村", sceneOrder: 1,
    description: "夜景", aliases: ["第2集 · 分镜1 · 图片", "Episode 2 · Shot 1 · Image", "分镜 1"], updatedAt: null,
  };
  assert.equal(matchesResource(resource, "第2集 分镜1"), true);
  assert.equal(matchesResource(resource, " 山村 夜景 "), true);
  assert.equal(matchesResource(resource, "EPISODE 2 SHOT"), true);
  assert.equal(matchesResource(resource, "第1集"), false);
  assert.equal(localizeResource(resource, "en").label, resource.aliases[1]);
  assert.equal(localizeResource(resource, "en").id, resource.id);
});

test("extra terms make the displayed media and kind labels searchable", () => {
  const character: ProjectResource = {
    kind: "character", id: "li-lei", label: "李雷", media: "image", url: "/character",
    episodeId: null, episodeNumber: null, episodeTitle: "", sceneOrder: null,
    description: "", aliases: [], updatedAt: null,
  };
  const typeTerms = ["图片", "Image", "角色", "Character"];
  assert.equal(matchesResource(character, "图片"), false);
  assert.equal(matchesResource(character, "图片", typeTerms), true);
  assert.equal(matchesResource(character, "character 李", typeTerms), true);
  assert.equal(matchesResource(character, "视频", typeTerms), false);
  assert.equal(matchesResource(character, "", typeTerms), true);
});
