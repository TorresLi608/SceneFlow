import { NextRequest, NextResponse } from "next/server";

import { listAdminUsersByBff } from "@/bff/admin-bff";
import { toBffErrorResponse } from "@/bff/route-error";

export async function GET(request: NextRequest) {
  try {
    const authorization = request.headers.get("authorization") ?? undefined;
    const data = await listAdminUsersByBff(authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
