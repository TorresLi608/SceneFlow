import type {
  CreateUserConfigInput,
  UpdateUserConfigInput,
  ValidateUserConfigInput,
  ValidateUserConfigResponse,
  UserConfigItemResponse,
  UserConfigListResponse,
} from "@/types/auth";
import { authConfig, backendClient } from "@/lib/http/backend-client";

export async function getUserConfigsByBff(authorization?: string) {
  const response = await backendClient.get<UserConfigListResponse>("/api/settings/keys", authConfig(authorization));

  return response.data;
}

export async function createUserConfigByBff(
  payload: CreateUserConfigInput,
  authorization?: string
) {
  const response = await backendClient.post<UserConfigItemResponse>("/api/settings/keys", payload, authConfig(authorization));

  return response.data;
}

export async function validateUserConfigByBff(
  payload: ValidateUserConfigInput,
  authorization?: string
) {
  const response = await backendClient.post<ValidateUserConfigResponse>(
    "/api/settings/keys/validate",
    payload,
    authConfig(authorization)
  );

  return response.data;
}

export async function updateUserConfigByBff(
  id: number,
  payload: UpdateUserConfigInput,
  authorization?: string
) {
  const response = await backendClient.patch<UserConfigItemResponse>(`/api/settings/keys/${id}`, payload, authConfig(authorization));

  return response.data;
}

export async function deleteUserConfigByBff(id: number, authorization?: string) {
  await backendClient.delete(`/api/settings/keys/${id}`, authConfig(authorization));
}

export async function activateOfficialConfigByBff(id: number, authorization?: string) {
  const response = await backendClient.post<UserConfigItemResponse>(
    `/api/settings/official/${id}/activate`,
    {},
    authConfig(authorization)
  );

  return response.data;
}
