import { NextRequest, NextResponse } from "next/server";

import { toBffErrorResponse } from "@/bff/route-error";
import { generateVideoByBff } from "@/bff/videos-bff";

export const maxDuration = 900;

export async function POST(request: NextRequest) {
  try {
    const authorization = request.headers.get("authorization") ?? undefined;
    const payload = await request.json().catch(() => ({}));
    const data = await generateVideoByBff(payload, authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
