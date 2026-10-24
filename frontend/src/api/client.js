import axios from "axios";

const baseURL = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const api = axios.create({
  baseURL: `${baseURL.replace(/\/$/, "")}/api`,
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

let accessToken = null;
let onAuthExpired = () => {};
let refreshInFlight = null;

export function setAccessToken(token) {
  accessToken = token;
}

export function setAuthExpiredHandler(handler) {
  onAuthExpired = handler;
}

export function refreshAccessToken() {
  if (!refreshInFlight) {
    refreshInFlight = axios
      .post(`${api.defaults.baseURL}/auth/refresh`, {}, { withCredentials: true })
      .then((response) => response.data.access_token)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

api.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const isAuthRequest = /\/auth\/(login|register|refresh|logout)$/.test(
      original?.url || "",
    );
    if (error.response?.status === 401 && original && !original._retried && !isAuthRequest) {
      original._retried = true;
      try {
        const freshToken = await refreshAccessToken();
        setAccessToken(freshToken);
        original.headers.Authorization = `Bearer ${freshToken}`;
        return api(original);
      } catch (refreshError) {
        setAccessToken(null);
        onAuthExpired();
        return Promise.reject(refreshError);
      }
    }

    const messages = {
      403: "You do not have permission to do that.",
      404: "That item could not be found.",
      413: "The uploaded file is too large.",
      422: "Please check the information and try again.",
      429: "Too many requests. Wait a moment and try again.",
    };
    if (error.response?.status >= 500) {
      error.userMessage = "The service is temporarily unavailable. Please try again.";
    } else if (error.response?.status === 403 && typeof error.response.data?.detail === "string") {
      error.userMessage = error.response.data.detail;
    } else {
      error.userMessage =
        messages[error.response?.status] ||
        error.response?.data?.detail ||
        "The request could not be completed.";
    }
    return Promise.reject(error);
  },
);
