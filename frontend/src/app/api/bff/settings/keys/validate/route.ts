import { NextRequest, NextResponse } from "next/server";

import { toBffErrorResponse } from "@/bff/route-error";
import { validateUserConfigByBff } from "@/bff/settings-bff";

export async function POST(request: NextRequest) {
  try {
    const authorization = request.headers.get("authorization") ?? undefined;
    const payload = await request.json();
    const data = await validateUserConfigByBff(payload, authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
