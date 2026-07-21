import { httpClient } from "@/lib/http/client";
import type { RedeemCodeResponse, UpdateMeInput, UserMeResponse } from "@/types/auth";

export async function getMeAction() {
  const response = await httpClient.get<UserMeResponse>("/api/bff/users/me");
  return response.data;
}

export async function updateMeAction(payload: UpdateMeInput) {
  const response = await httpClient.patch<UserMeResponse>("/api/bff/users/me", payload);
  return response.data;
}

export async function changePasswordAction(currentPassword: string, password: string) {
  const response = await httpClient.patch<UserMeResponse>("/api/bff/users/me", { currentPassword, password });
  return response.data;
}

export async function redeemCodeAction(code: string) {
  const response = await httpClient.post<RedeemCodeResponse>("/api/bff/users/redeem", { code });
  return response.data;
}
