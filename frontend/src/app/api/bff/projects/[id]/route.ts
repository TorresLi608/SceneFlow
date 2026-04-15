import { NextRequest, NextResponse } from "next/server";

import { deleteProjectByBff } from "@/bff/projects-bff";
import { toBffErrorResponse } from "@/bff/route-error";

interface Context {
  params: Promise<{ id: string }>;
}

export async function DELETE(request: NextRequest, context: Context) {
  try {
    const { id } = await context.params;
    const authorization = request.headers.get("authorization") ?? undefined;

    await deleteProjectByBff(id, authorization);
    return new NextResponse(null, { status: 204 });
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
