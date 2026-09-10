import assert from "node:assert/strict";
import test from "node:test";
import type { UIMessage } from "ai";

// @ts-expect-error Node's type stripping executes this TypeScript source directly.
import { clearFailedReasoning } from "./chat-message-state.ts";

test("a failed turn clears only its reasoning and retains history and partial text", () => {
  const history: UIMessage[] = [
    { id: "previous", role: "assistant", parts: [{ type: "reasoning", text: "Earlier reasoning" }, { type: "text", text: "Earlier answer" }] },
    { id: "question", role: "user", parts: [{ type: "text", text: "Next question" }] },
  ];
  const partial: UIMessage = {
    id: "failed",
    role: "assistant",
    parts: [{ type: "reasoning", text: "Unfinished reasoning", state: "streaming" }, { type: "text", text: "Partial answer", state: "streaming" }],
  };
  const messages = [...history, partial];
  const result = clearFailedReasoning(messages);

  assert.deepEqual(result, [...history, { ...partial, parts: [partial.parts[1]] }]);
  assert.equal(result[0], history[0]);
  assert.equal(messages.at(-1)?.parts.length, 2);
  assert.equal(clearFailedReasoning(history), history);
  assert.deepEqual(clearFailedReasoning([]), []);
});
