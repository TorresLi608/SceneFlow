import { httpClient } from "@/lib/http/client";
import type {
  AuthResponse,
  RegisterInput,
  SendVerificationCodeInput,
  SendVerificationCodeResponse,
} from "@/types/auth";

interface AuthPayload {
  username: string;
  password: string;
}

export async function loginAction(payload: AuthPayload) {
  const response = await httpClient.post<AuthResponse>("/api/bff/auth/login", payload);
  return response.data;
}

export async function sendVerificationCodeAction(payload: SendVerificationCodeInput) {
  const response = await httpClient.post<SendVerificationCodeResponse>(
    "/api/bff/auth/send-verification-code",
    payload
  );
  return response.data;
}

export async function registerAction(payload: RegisterInput) {
  const response = await httpClient.post<AuthResponse>("/api/bff/auth/register", payload);
  return response.data;
}
