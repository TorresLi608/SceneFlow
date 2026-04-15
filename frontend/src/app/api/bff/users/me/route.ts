import { NextRequest, NextResponse } from "next/server";

import { toBffErrorResponse } from "@/bff/route-error";
import { getMeByBff } from "@/bff/user-bff";

export async function GET(request: NextRequest) {
  try {
    const authorization = request.headers.get("authorization") ?? undefined;
    const data = await getMeByBff(authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
