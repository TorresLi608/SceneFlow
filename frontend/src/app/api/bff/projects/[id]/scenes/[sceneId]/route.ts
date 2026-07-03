import { NextRequest, NextResponse } from "next/server";

import { updateProjectSceneByBff } from "@/bff/projects-bff";
import { toBffErrorResponse } from "@/bff/route-error";

interface Context {
  params: Promise<{ id: string; sceneId: string }>;
}

export async function PATCH(request: NextRequest, context: Context) {
  try {
    const { id, sceneId } = await context.params;
    const authorization = request.headers.get("authorization") ?? undefined;
    const payload = await request.json();
    const data = await updateProjectSceneByBff(id, sceneId, payload, authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
