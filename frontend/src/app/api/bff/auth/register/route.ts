import { NextRequest, NextResponse } from "next/server";

import { registerByBff } from "@/bff/auth-bff";
import { toBffErrorResponse } from "@/bff/route-error";

export async function POST(request: NextRequest) {
  try {
    const payload = await request.json();
    const data = await registerByBff(payload);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
