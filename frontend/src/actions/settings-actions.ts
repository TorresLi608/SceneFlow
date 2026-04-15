import { httpClient } from "@/lib/http/client";
import type {
  CreateUserConfigInput,
  ValidateUserConfigInput,
  ValidateUserConfigResponse,
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

export async function validateUserConfigAction(payload: ValidateUserConfigInput) {
  const response = await httpClient.post<ValidateUserConfigResponse>(
    "/api/bff/settings/keys/validate",
    payload
  );
  return response.data;
}
