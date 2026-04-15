import axios from "axios";

const backendBaseURL =
  process.env.BACKEND_API_BASE_URL?.trim() ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ||
  "http://127.0.0.1:8080";

export const backendClient = axios.create({
  baseURL: backendBaseURL,
  timeout: 15000,
});
