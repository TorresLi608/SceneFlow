import { NextRequest, NextResponse } from "next/server";

import { createInvitationCodeByBff, listInvitationCodesByBff } from "@/bff/admin-bff";
import { toBffErrorResponse } from "@/bff/route-error";
import type { InvitationCodeDays } from "@/types/admin";

export async function GET(request: NextRequest) {
  try {
    const authorization = request.headers.get("authorization") ?? undefined;
    return NextResponse.json(await listInvitationCodesByBff(authorization));
  } catch (error) {
    return toBffErrorResponse(error);
  }
}

export async function POST(request: NextRequest) {
  try {
    const authorization = request.headers.get("authorization") ?? undefined;
    const { days } = await request.json();
    const data = await createInvitationCodeByBff(days as InvitationCodeDays, authorization);
    return NextResponse.json(data, { status: 201 });
  } catch (error) {
    return toBffErrorResponse(error);
  }
}
