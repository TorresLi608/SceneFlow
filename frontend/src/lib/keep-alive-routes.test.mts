import assert from "node:assert/strict";
import test from "node:test";

// @ts-expect-error Node's type stripping executes this TypeScript source directly.
import { KEEP_ALIVE_ROUTES, matchKeepAliveRoute, withVisitedRoute } from "./keep-alive-routes.ts";

test("only the generation and chat menus are kept alive", () => {
  assert.deepEqual([...KEEP_ALIVE_ROUTES], ["/chat", "/images", "/audio", "/videos"]);
  assert.equal(matchKeepAliveRoute("/chat"), "/chat");
  assert.equal(matchKeepAliveRoute("/videos/"), "/videos");
  assert.equal(matchKeepAliveRoute("/videos-archive"), null);
  assert.equal(matchKeepAliveRoute("/usage"), null);
  assert.equal(matchKeepAliveRoute("/admin/models"), null);
  assert.equal(matchKeepAliveRoute("/projects/abc/videos"), null);
});

test("visited routes accumulate in visit order and never duplicate", () => {
  const initial = withVisitedRoute([], "/videos");
  assert.deepEqual(initial, ["/videos"]);

  const unchanged = withVisitedRoute(initial, "/videos");
  assert.equal(unchanged, initial);
  assert.equal(withVisitedRoute(initial, null), initial);

  const extended = withVisitedRoute(initial, "/chat");
  assert.deepEqual(extended, ["/videos", "/chat"]);
  assert.deepEqual(initial, ["/videos"]);
});
