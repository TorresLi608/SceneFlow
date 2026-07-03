import { NextRequest, NextResponse } from "next/server";

import { deleteChatSessionByBff } from "@/bff/chat-bff";
import { toBffErrorResponse } from "@/bff/route-error";

interface Context {
  params: Promise<{ id: string }>;
}

export async function DELETE(request: NextRequest, context: Context) {
  try {
    const authorization = request.headers.get("authorization") ?? undefined;
    const { id } = await context.params;
    const data = await deleteChatSessionByBff(id, authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
