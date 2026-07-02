import { NextRequest, NextResponse } from "next/server";

import { deleteOfficialConfigByBff, updateOfficialConfigByBff } from "@/bff/admin-bff";
import { toBffErrorResponse } from "@/bff/route-error";

interface Context {
  params: Promise<{ id: string }>;
}

export async function PATCH(request: NextRequest, context: Context) {
  try {
    const { id } = await context.params;
    const authorization = request.headers.get("authorization") ?? undefined;
    const payload = await request.json();
    const data = await updateOfficialConfigByBff(Number(id), payload, authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}

export async function DELETE(request: NextRequest, context: Context) {
  try {
    const { id } = await context.params;
    const authorization = request.headers.get("authorization") ?? undefined;
    await deleteOfficialConfigByBff(Number(id), authorization);
    return new NextResponse(null, { status: 204 });
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
