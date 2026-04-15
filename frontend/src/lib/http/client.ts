import axios, { AxiosHeaders } from "axios";

import { useUserStore } from "@/store/user-store";

const BFF_BASE_URL = process.env.NEXT_PUBLIC_BFF_BASE_URL?.trim() || "";

export const httpClient = axios.create({
  baseURL: BFF_BASE_URL,
  timeout: 90000,
});

httpClient.interceptors.request.use((config) => {
  const token = useUserStore.getState().token;

  if (token) {
    if (!config.headers) {
      config.headers = new AxiosHeaders();
    }

    config.headers.set("Authorization", `Bearer ${token}`);
  }

  return config;
});

httpClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useUserStore.getState().logout();
    }

    return Promise.reject(error);
  }
);
