import { NextRequest, NextResponse } from "next/server";

import { reorderProjectScenesByBff } from "@/bff/projects-bff";
import { toBffErrorResponse } from "@/bff/route-error";

interface Context {
  params: Promise<{ id: string }>;
}

export async function PATCH(request: NextRequest, context: Context) {
  try {
    const { id } = await context.params;
    const authorization = request.headers.get("authorization") ?? undefined;
    const payload = await request.json();
    const data = await reorderProjectScenesByBff(id, payload, authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
