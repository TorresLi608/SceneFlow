import { httpClient } from "@/lib/http/client";
import type { AuthResponse } from "@/types/auth";

interface AuthPayload {
  username: string;
  password: string;
}

export async function loginAction(payload: AuthPayload) {
  const response = await httpClient.post<AuthResponse>("/api/bff/auth/login", payload);
  return response.data;
}

export async function registerAction(payload: AuthPayload) {
  const response = await httpClient.post<AuthResponse>("/api/bff/auth/register", payload);
  return response.data;
}
