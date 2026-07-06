import { NextRequest } from "next/server";
import { createUIMessageStream, createUIMessageStreamResponse } from "ai";

import { backendBaseURL } from "@/lib/http/backend-client";
import type { ChatAgentStep, ChatMessage } from "@/types/chat";

interface Context {
  params: Promise<{ id: string }>;
}

type BackendStreamEvent =
  | { type: "userMessage"; message: ChatMessage }
  | { type: "agent_step"; step: ChatAgentStep }
  | { type: "reasoning_delta"; content: string }
  | { type: "content_delta"; content: string }
  | { type: "assistantMessage"; message: ChatMessage }
  | { type: "error"; error: string };

async function readNdjson(stream: ReadableStream<Uint8Array>, onEvent: (event: BackendStreamEvent) => void) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.trim()) {
        onEvent(JSON.parse(line) as BackendStreamEvent);
      }
    }
  }

  if (buffer.trim()) {
    onEvent(JSON.parse(buffer) as BackendStreamEvent);
  }
}

export async function POST(request: NextRequest, context: Context) {
  const { id } = await context.params;
  const authorization = request.headers.get("authorization") ?? "";
  const upstream = await fetch(`${backendBaseURL}/api/chat/sessions/${id}/messages/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(authorization ? { Authorization: authorization } : {}),
    },
    body: await request.text(),
  });

  if (!upstream.ok || !upstream.body) {
    return new Response(await upstream.text().catch(() => "stream request failed"), { status: upstream.status });
  }

  return createUIMessageStreamResponse({
    stream: createUIMessageStream({
      async execute({ writer }) {
        let textStarted = false;
        let reasoningStarted = false;
        let textEnded = false;
        let reasoningEnded = false;

        writer.write({ type: "start" });

        await readNdjson(upstream.body!, (event) => {
          if (event.type === "agent_step") {
            writer.write({ type: "data-agent_step", data: event.step, transient: true });
            return;
          }

          if (event.type === "reasoning_delta") {
            if (!reasoningStarted) {
              writer.write({ type: "reasoning-start", id: "reasoning" });
              reasoningStarted = true;
            }
            writer.write({ type: "reasoning-delta", id: "reasoning", delta: event.content });
            return;
          }

          if (event.type === "content_delta") {
            if (!textStarted) {
              writer.write({ type: "text-start", id: "text" });
              textStarted = true;
            }
            writer.write({ type: "text-delta", id: "text", delta: event.content });
            return;
          }

          if (event.type === "assistantMessage") {
            if (reasoningStarted && !reasoningEnded) {
              writer.write({ type: "reasoning-end", id: "reasoning" });
              reasoningEnded = true;
            }
            if (!textStarted && event.message.content) {
              writer.write({ type: "text-start", id: "text" });
              writer.write({ type: "text-delta", id: "text", delta: event.message.content });
              textStarted = true;
            }
            if (textStarted && !textEnded) {
              writer.write({ type: "text-end", id: "text" });
              textEnded = true;
            }
            writer.write({ type: "message-metadata", messageMetadata: { chatMessage: event.message } });
            return;
          }

          if (event.type === "error") {
            writer.write({ type: "error", errorText: event.error });
          }
        });

        if (reasoningStarted && !reasoningEnded) {
          writer.write({ type: "reasoning-end", id: "reasoning" });
        }
        if (textStarted && !textEnded) {
          writer.write({ type: "text-end", id: "text" });
        }
        writer.write({ type: "finish", finishReason: "stop" });
      },
      onError: (error) => error instanceof Error ? error.message : "stream request failed",
    }),
  });
}
