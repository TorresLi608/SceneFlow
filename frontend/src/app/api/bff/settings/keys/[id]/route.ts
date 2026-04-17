import { NextRequest, NextResponse } from "next/server";

import { deleteUserConfigByBff, updateUserConfigByBff } from "@/bff/settings-bff";
import { toBffErrorResponse } from "@/bff/route-error";

interface RouteContext {
  params: Promise<{ id: string }>;
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  try {
    const authorization = request.headers.get("authorization") ?? undefined;
    const payload = await request.json();
    const { id } = await context.params;
    const data = await updateUserConfigByBff(Number(id), payload, authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  try {
    const authorization = request.headers.get("authorization") ?? undefined;
    const { id } = await context.params;
    await deleteUserConfigByBff(Number(id), authorization);
    return new NextResponse(null, { status: 204 });
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
