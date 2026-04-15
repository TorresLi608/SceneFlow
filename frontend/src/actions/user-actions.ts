import { httpClient } from "@/lib/http/client";
import type { UserMeResponse } from "@/types/auth";

export async function getMeAction() {
  const response = await httpClient.get<UserMeResponse>("/api/bff/users/me");
  return response.data;
}
