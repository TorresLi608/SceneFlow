import { NextRequest, NextResponse } from "next/server";

import { toBffErrorResponse } from "@/bff/route-error";
import { activateOfficialConfigByBff } from "@/bff/settings-bff";

interface Context {
  params: Promise<{ id: string }>;
}

export async function POST(request: NextRequest, context: Context) {
  try {
    const { id } = await context.params;
    const authorization = request.headers.get("authorization") ?? undefined;
    const data = await activateOfficialConfigByBff(Number(id), authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
