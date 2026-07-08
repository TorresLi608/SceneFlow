import { NextRequest, NextResponse } from "next/server";

import { generateImageByBff } from "@/bff/images-bff";
import { toBffErrorResponse } from "@/bff/route-error";

export async function POST(request: NextRequest) {
  try {
    const authorization = request.headers.get("authorization") ?? undefined;
    const payload = await request.json().catch(() => ({}));
    const data = await generateImageByBff(payload, authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
