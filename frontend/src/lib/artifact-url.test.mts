import assert from "node:assert/strict";
import test from "node:test";

// @ts-expect-error Node's type stripping executes this TypeScript source directly.
import { artifactBffUrl, rewriteArtifactLinks } from "./artifact-url.ts";

test("rewrites backend-origin artifact links in chat Markdown to the page origin BFF", () => {
  const origin = "https://sceneflow.example.com";
  assert.equal(
    rewriteArtifactLinks(
      "已生成：[需求文档.docx](http://127.0.0.1:8080/api/chat/artifacts/a.b-c_d)\n\n![图](http://backend:8080/api/chat/artifacts/e.f.g)",
      origin,
    ),
    "已生成：[需求文档.docx](https://sceneflow.example.com/api/bff/chat/artifacts/a.b-c_d)\n\n![图](https://sceneflow.example.com/api/bff/chat/artifacts/e.f.g)",
  );
  // Trailing slash on the origin, unrelated links, and already-proxied links are handled or left alone.
  assert.equal(
    rewriteArtifactLinks("[x](https://api.example.com/api/chat/artifacts/t)", `${origin}/`),
    "[x](https://sceneflow.example.com/api/bff/chat/artifacts/t)",
  );
  const untouched = "[doc](https://cdn.example.com/a.pdf) [y](https://sceneflow.example.com/api/bff/chat/artifacts/t)";
  assert.equal(rewriteArtifactLinks(untouched, origin), untouched);
  // No origin during server render: keep the stored text.
  const stored = "[x](http://127.0.0.1:8080/api/chat/artifacts/t)";
  assert.equal(rewriteArtifactLinks(stored, ""), stored);
});

test("routes backend artifact links through the same-origin BFF", () => {
  assert.equal(
    artifactBffUrl("http://127.0.0.1:8080/api/chat/artifacts/token-1"),
    "/api/bff/chat/artifacts/token-1",
  );
  assert.equal(artifactBffUrl("/api/chat/artifacts/token-2"), "/api/bff/chat/artifacts/token-2");
  assert.equal(artifactBffUrl("https://cdn.example.com/result.png"), "https://cdn.example.com/result.png");
});
