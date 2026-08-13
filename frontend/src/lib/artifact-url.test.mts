import assert from "node:assert/strict";
import test from "node:test";

// @ts-expect-error Node's type stripping executes this TypeScript source directly.
import { artifactBffUrl } from "./artifact-url.ts";

test("routes backend artifact links through the same-origin BFF", () => {
  assert.equal(
    artifactBffUrl("http://127.0.0.1:8080/api/chat/artifacts/token-1"),
    "/api/bff/chat/artifacts/token-1",
  );
  assert.equal(artifactBffUrl("/api/chat/artifacts/token-2"), "/api/bff/chat/artifacts/token-2");
  assert.equal(artifactBffUrl("https://cdn.example.com/result.png"), "https://cdn.example.com/result.png");
});
