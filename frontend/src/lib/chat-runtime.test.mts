import assert from "node:assert/strict";
import test from "node:test";

// @ts-expect-error Node's type stripping executes this TypeScript source directly.
import { markRunningStepsStopped, runningSessionIds, upsertAgentStep } from "./chat-runtime.ts";

test("upsertAgentStep updates a step in place and appends new ones", () => {
  const running = { id: "search", label: "搜索", status: "running" as const };
  const steps = upsertAgentStep([], running);
  assert.deepEqual(steps, [running]);

  const done = { ...running, status: "done" as const, detail: "3 results" };
  const updated = upsertAgentStep(steps, done);
  assert.deepEqual(updated, [done]);

  const appended = upsertAgentStep(updated, { id: "fetch", label: "抓取", status: "running" });
  assert.equal(appended.length, 2);
  assert.equal(appended[0], done);
});

test("markRunningStepsStopped only touches running steps and keeps the array when nothing runs", () => {
  const finished = [{ id: "a", label: "A", status: "done" as const }];
  assert.equal(markRunningStepsStopped(finished, "stopped"), finished);

  const mixed = [...finished, { id: "b", label: "B", status: "running" as const }];
  assert.deepEqual(markRunningStepsStopped(mixed, "已停止"), [
    finished[0],
    { id: "b", label: "B", status: "stopped", detail: "已停止" },
  ]);
});

test("runningSessionIds lists sending sessions and skips the new-chat placeholder", () => {
  const sessions = {
    "new-chat": { isSending: true },
    one: { isSending: true },
    two: { isSending: false },
    three: { isSending: true },
  };
  assert.deepEqual(runningSessionIds(sessions, "new-chat"), ["one", "three"]);
  assert.deepEqual(runningSessionIds({}, "new-chat"), []);
});
