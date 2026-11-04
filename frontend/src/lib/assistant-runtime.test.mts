import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { useExternalStoreRuntime, type AssistantRuntime, type ExternalThreadMessage } from "@assistant-ui/react";

function createRuntime(): AssistantRuntime {
  let runtime!: AssistantRuntime;
  function Probe() {
    runtime = useExternalStoreRuntime<ExternalThreadMessage>({ messages: [], onNew: async () => {} });
    return null;
  }
  renderToString(createElement(Probe));
  return runtime;
}

test("assistant runtime snapshots stay cached before and after resubscription", () => {
  const runtime = createRuntime();
  // Activity disconnects effects. Identity must also hold with no subscribers.
  for (const store of [runtime.threads, runtime.thread, runtime.thread.composer]) {
    for (let cycle = 0; cycle < 3; cycle++) {
      assert.strictEqual(store.getState(), store.getState());
      const unsubscribe = store.subscribe(() => {});
      assert.strictEqual(store.getState(), store.getState());
      unsubscribe();
      assert.strictEqual(store.getState(), store.getState());
    }
  }
});

test("composer drafts update and survive subscription cleanup", () => {
  const composer = createRuntime().thread.composer;
  const initial = composer.getState();
  const unsubscribe = composer.subscribe(() => {});
  composer.setText("unsent draft");
  const draft = composer.getState();
  assert.notStrictEqual(draft, initial);
  assert.equal(draft.text, "unsent draft");
  unsubscribe();
  assert.strictEqual(composer.getState(), draft);
  const resubscribe = composer.subscribe(() => {});
  assert.strictEqual(composer.getState(), draft);
  composer.setText("edited draft");
  assert.equal(composer.getState().text, "edited draft");
  resubscribe();
});
