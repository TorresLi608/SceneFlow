import { NextRequest, NextResponse } from "next/server";

import { listChatMessagesByBff, sendChatMessageByBff } from "@/bff/chat-bff";
import { toBffErrorResponse } from "@/bff/route-error";

interface Context {
  params: Promise<{ id: string }>;
}

export async function GET(request: NextRequest, context: Context) {
  try {
    const { id } = await context.params;
    const authorization = request.headers.get("authorization") ?? undefined;
    const data = await listChatMessagesByBff(id, authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}

export async function POST(request: NextRequest, context: Context) {
  try {
    const { id } = await context.params;
    const authorization = request.headers.get("authorization") ?? undefined;
    const payload = await request.json();
    const data = await sendChatMessageByBff(id, payload, authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
