import { NextRequest, NextResponse } from "next/server";

import { deleteAdminUserByBff, resetAdminUserPasswordByBff, updateAdminUserByBff } from "@/bff/admin-bff";
import { toBffErrorResponse } from "@/bff/route-error";

interface Context {
  params: Promise<{ id: string }>;
}

export async function PATCH(request: NextRequest, context: Context) {
  try {
    const { id } = await context.params;
    const authorization = request.headers.get("authorization") ?? undefined;
    const payload = await request.json();
    const data = await updateAdminUserByBff(Number(id), payload, authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}

export async function POST(request: NextRequest, context: Context) {
  try {
    const { id } = await context.params;
    const authorization = request.headers.get("authorization") ?? undefined;
    const data = await resetAdminUserPasswordByBff(Number(id), authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}

export async function DELETE(request: NextRequest, context: Context) {
  try {
    const { id } = await context.params;
    const authorization = request.headers.get("authorization") ?? undefined;
    await deleteAdminUserByBff(Number(id), authorization);
    return new NextResponse(null, { status: 204 });
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
