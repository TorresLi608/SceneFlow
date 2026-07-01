import { NextRequest } from "next/server";

import { backendBaseURL } from "@/lib/http/backend-client";

interface Context {
  params: Promise<{ id: string }>;
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

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "application/x-ndjson",
    },
  });
}
