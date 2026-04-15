import { NextRequest, NextResponse } from "next/server";

import { toBffErrorResponse } from "@/bff/route-error";
import { createUserConfigByBff, getUserConfigsByBff } from "@/bff/settings-bff";

export async function GET(request: NextRequest) {
  try {
    const authorization = request.headers.get("authorization") ?? undefined;
    const data = await getUserConfigsByBff(authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}

export async function POST(request: NextRequest) {
  try {
    const authorization = request.headers.get("authorization") ?? undefined;
    const payload = await request.json();
    const data = await createUserConfigByBff(payload, authorization);
    return NextResponse.json(data, { status: 201 });
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
