import axios from "axios";
import { NextResponse } from "next/server";

export function toBffErrorResponse(error: unknown) {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status ?? 500;
    const payload = error.response?.data ?? {
      error: error.message || "upstream request failed",
    };

    return NextResponse.json(payload, { status });
  }

  return NextResponse.json({ error: "internal bff error" }, { status: 500 });
}
