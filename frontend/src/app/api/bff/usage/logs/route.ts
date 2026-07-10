import { NextRequest, NextResponse } from "next/server";

import { toBffErrorResponse } from "@/bff/route-error";
import { listUsageLogsByBff } from "@/bff/usage-bff";

export async function GET(request: NextRequest) {
  try {
    const authorization = request.headers.get("authorization") ?? undefined;
    const feature = request.nextUrl.searchParams.get("feature") || "all";
    const days = Number(request.nextUrl.searchParams.get("days") || 30);
    const data = await listUsageLogsByBff(feature, days, authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
