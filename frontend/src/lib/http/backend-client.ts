import axios from "axios";
import type { AxiosRequestConfig } from "axios";

export const backendBaseURL =
  process.env.BACKEND_API_BASE_URL?.trim() ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ||
  "http://127.0.0.1:8080";

export const backendClient = axios.create({
  baseURL: backendBaseURL,
  timeout: 90000,
});

export function authConfig(authorization?: string): AxiosRequestConfig | undefined {
  return authorization ? { headers: { Authorization: authorization } } : undefined;
}
