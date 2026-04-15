import { NextRequest, NextResponse } from "next/server";

import { loginByBff } from "@/bff/auth-bff";
import { toBffErrorResponse } from "@/bff/route-error";

export async function POST(request: NextRequest) {
  try {
    const payload = await request.json();
    const data = await loginByBff(payload);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
