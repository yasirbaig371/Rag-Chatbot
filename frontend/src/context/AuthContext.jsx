import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  api,
  refreshAccessToken,
  setAccessToken,
  setAuthExpiredHandler,
} from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const clearAuth = useCallback(() => {
    setAccessToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    setAuthExpiredHandler(clearAuth);
    return () => setAuthExpiredHandler(() => {});
  }, [clearAuth]);

  useEffect(() => {
    let active = true;
    refreshAccessToken()
      .then((token) => {
        setAccessToken(token);
        return api.get("/auth/me");
      })
      .then(({ data }) => {
        if (active) setUser(data);
      })
      .catch(() => {
        clearAuth();
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [clearAuth]);

  const login = useCallback(async (credentials) => {
    const { data } = await api.post("/auth/login", credentials);
    setAccessToken(data.access_token);
    const profile = await api.get("/auth/me");
    setUser(profile.data);
    return profile.data;
  }, []);

  const refreshProfile = useCallback(async () => {
    const { data } = await api.get("/auth/me");
    setUser(data);
    return data;
  }, []);

  const register = useCallback(async (details) => {
    const { data: account } = await api.post("/auth/register", details);
    if (!account.is_active) return account;
    return login({ email: details.email, password: details.password });
  }, [login]);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      clearAuth();
    }
  }, [clearAuth]);

  const value = useMemo(
    () => ({ user, loading, login, register, logout, clearAuth, refreshProfile }),
    [user, loading, login, register, logout, clearAuth, refreshProfile],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}
