import { NextRequest, NextResponse } from "next/server";

import { createProjectByBff, getProjectsByBff } from "@/bff/projects-bff";
import { toBffErrorResponse } from "@/bff/route-error";

export async function GET(request: NextRequest) {
  try {
    const authorization = request.headers.get("authorization") ?? undefined;
    const data = await getProjectsByBff(authorization);
    return NextResponse.json(data);
  } catch (error) {
    return toBffErrorResponse(error);
  }
}

export async function POST(request: NextRequest) {
  try {
    const authorization = request.headers.get("authorization") ?? undefined;
    const payload = await request.json();
    const data = await createProjectByBff(payload, authorization);
    return NextResponse.json(data, { status: 201 });
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
