import type { UserMeResponse } from "@/types/auth";
import { backendClient } from "@/lib/http/backend-client";

export async function getMeByBff(authorization?: string) {
  const response = await backendClient.get<UserMeResponse>("/api/users/me", {
    headers: {
      Authorization: authorization,
    },
  });

  return response.data;
}
