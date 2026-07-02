import { NextRequest, NextResponse } from "next/server";

import { createOfficialConfigByBff, listOfficialConfigsByBff } from "@/bff/admin-bff";
import { toBffErrorResponse } from "@/bff/route-error";

export async function GET(request: NextRequest) {
  try {
    const authorization = request.headers.get("authorization") ?? undefined;
    const data = await listOfficialConfigsByBff(authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}

export async function POST(request: NextRequest) {
  try {
    const authorization = request.headers.get("authorization") ?? undefined;
    const payload = await request.json();
    const data = await createOfficialConfigByBff(payload, authorization);
    return NextResponse.json(data, { status: 201 });
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
