"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  apiGet,
  apiPost,
  clearToken,
  getToken,
  setToken,
} from "./api";
import type { LoginResponse, Role, User } from "./types";

interface AuthContextValue {
  user: User | null;
  token: string | null;
  role: Role | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => void;
  isAdmin: boolean;
  isHR: boolean;
  isDeliveryManager: boolean;
  /** HR or Admin can perform candidate write actions. */
  canManageCandidates: boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setTokenState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Hydrate from localStorage on mount.
  useEffect(() => {
    let active = true;
    const stored = getToken();
    if (!stored) {
      setLoading(false);
      return;
    }
    setTokenState(stored);
    apiGet<User>("/auth/me")
      .then((u) => {
        if (active) setUser(u);
      })
      .catch(() => {
        if (active) {
          clearToken();
          setTokenState(null);
          setUser(null);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await apiPost<LoginResponse>("/auth/login", {
      email,
      password,
    });
    setToken(res.access_token);
    setTokenState(res.access_token);
    setUser(res.user);
    return res.user;
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setTokenState(null);
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(() => {
    const role = user?.role ?? null;
    return {
      user,
      token,
      role,
      loading,
      login,
      logout,
      isAdmin: role === "ADMIN",
      isHR: role === "HR",
      isDeliveryManager: role === "DELIVERY_MANAGER",
      canManageCandidates: role === "HR" || role === "ADMIN",
    };
  }, [user, token, loading, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
