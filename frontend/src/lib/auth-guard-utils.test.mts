import assert from "node:assert/strict";
import test from "node:test";

// @ts-expect-error Node's type stripping executes this TypeScript source directly.
import { buildLoginRedirectUrl, isPublicRoute, resolveSafeRedirectUrl } from "./auth-guard-utils.ts";

test("isPublicRoute allows public authentication routes and protects workspace/projects routes", () => {
  assert.equal(isPublicRoute("/login"), true);
  assert.equal(isPublicRoute("/register"), true);

  assert.equal(isPublicRoute("/"), false);
  assert.equal(isPublicRoute("/chat"), false);
  assert.equal(isPublicRoute("/images"), false);
  assert.equal(isPublicRoute("/videos"), false);
  assert.equal(isPublicRoute("/ai-script"), false);
  assert.equal(isPublicRoute("/projects/proj-1/info"), false);
  assert.equal(isPublicRoute("/projects/proj-1/characters"), false);
  assert.equal(isPublicRoute("/projects/proj-1/episodes"), false);
  assert.equal(isPublicRoute("/projects/proj-1/episode/ep-1"), false);
  assert.equal(isPublicRoute("/projects/proj-1/workbench"), false);
});

test("buildLoginRedirectUrl appends encoded redirect target for protected paths", () => {
  assert.equal(
    buildLoginRedirectUrl("/projects/proj-123/episodes"),
    "/login?redirect=%2Fprojects%2Fproj-123%2Fepisodes"
  );
  assert.equal(
    buildLoginRedirectUrl("/projects/proj-123/episode/ep-456"),
    "/login?redirect=%2Fprojects%2Fproj-123%2Fepisode%2Fep-456"
  );
  assert.equal(buildLoginRedirectUrl("/"), "/login");
  assert.equal(buildLoginRedirectUrl(""), "/login");
});

test("resolveSafeRedirectUrl accepts valid internal paths and blocks open redirect vectors", () => {
  assert.equal(resolveSafeRedirectUrl("/projects/proj-123/info"), "/projects/proj-123/info");
  assert.equal(resolveSafeRedirectUrl("/chat"), "/chat");
  assert.equal(resolveSafeRedirectUrl(null), "/");
  assert.equal(resolveSafeRedirectUrl(undefined), "/");
  assert.equal(resolveSafeRedirectUrl(""), "/");

  // 阻断外部恶意重定向与伪协议
  assert.equal(resolveSafeRedirectUrl("//evil.com/phish"), "/");
  assert.equal(resolveSafeRedirectUrl("https://evil.com"), "/");
  assert.equal(resolveSafeRedirectUrl("javascript:alert(1)"), "/");
});
