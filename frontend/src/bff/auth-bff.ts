import type { AuthResponse } from "@/types/auth";
import { backendClient } from "@/lib/http/backend-client";

interface AuthPayload {
  username: string;
  password: string;
}

export async function loginByBff(payload: AuthPayload) {
  const response = await backendClient.post<AuthResponse>("/api/auth/login", payload);
  return response.data;
}

export async function registerByBff(payload: AuthPayload) {
  const response = await backendClient.post<AuthResponse>("/api/auth/register", payload);
  return response.data;
}
