import { NextResponse } from "next/server";

import { getProjectTemplatesByBff } from "@/bff/projects-bff";

export async function GET() {
  const data = await getProjectTemplatesByBff();
  return NextResponse.json(data);
}
