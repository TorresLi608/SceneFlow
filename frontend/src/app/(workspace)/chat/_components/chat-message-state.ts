import type { UIMessage } from "ai";

export function clearFailedReasoning<T extends UIMessage>(messages: T[]): T[] {
  const lastMessage = messages.at(-1);
  if (lastMessage?.role !== "assistant") return messages;

  return [
    ...messages.slice(0, -1),
    { ...lastMessage, parts: lastMessage.parts.filter((part) => part.type !== "reasoning") },
  ];
}
