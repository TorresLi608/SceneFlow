import type { UserMeResponse } from "@/types/auth";
import { authConfig, backendClient } from "@/lib/http/backend-client";

export async function getMeByBff(authorization?: string) {
  const response = await backendClient.get<UserMeResponse>("/api/users/me", authConfig(authorization));

  return response.data;
}
