import axios from "axios";

export function resolveRequestError(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const backendMessage = error.response?.data?.error;
    if (typeof backendMessage === "string" && backendMessage.trim()) {
      return backendMessage;
    }

    if (typeof error.message === "string" && error.message.trim()) {
      return error.message;
    }
  }

  return fallback;
}
