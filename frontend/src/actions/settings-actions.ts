import { httpClient } from "@/lib/http/client";
import type {
  CreateUserConfigInput,
  UserConfigItemResponse,
  UserConfigListResponse,
} from "@/types/auth";

export async function listUserConfigsAction() {
  const response = await httpClient.get<UserConfigListResponse>("/api/bff/settings/keys");
  return response.data;
}

export async function createUserConfigAction(payload: CreateUserConfigInput) {
  const response = await httpClient.post<UserConfigItemResponse>("/api/bff/settings/keys", payload);
  return response.data;
}
