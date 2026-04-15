import { NextRequest, NextResponse } from "next/server";

import { generateVideoByBff } from "@/bff/projects-bff";
import { toBffErrorResponse } from "@/bff/route-error";

interface Context {
  params: Promise<{ id: string }>;
}

export async function POST(request: NextRequest, context: Context) {
  try {
    const { id } = await context.params;
    const authorization = request.headers.get("authorization") ?? undefined;
    const payload = await request.json().catch(() => ({}));

    const data = await generateVideoByBff(id, payload, authorization);
    return NextResponse.json(data, { status: 202 });
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
