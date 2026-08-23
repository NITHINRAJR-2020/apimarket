import { createContext, useContext, useEffect, useState, ReactNode, useCallback } from "react";
import { api, setAuthToken, getAuthToken, setUnauthorizedHandler } from "../services/api";
import type { User, UserRole } from "../types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  signup: (name: string, email: string, password: string, role: UserRole) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    setAuthToken(null);
    setUser(null);
  }, []);

  // Register the central 401 handler once: any expired/invalid session
  // anywhere in the app drops us back to a logged-out state.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setAuthToken(null);
      setUser(null);
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  // On boot, if we have a stored token, restore the session by fetching /me.
  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then((u) => setUser(u))
      .catch(() => {
        setAuthToken(null);
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  async function login(email: string, password: string): Promise<User> {
    const res = await api.login({ email, password });
    setAuthToken(res.access_token);
    setUser(res.user);
    return res.user;
  }

  async function signup(name: string, email: string, password: string, role: UserRole): Promise<User> {
    const res = await api.signup({ name, email, password, role });
    setAuthToken(res.access_token);
    setUser(res.user);
    return res.user;
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

/** The home dashboard path for a given role. */
export function dashboardPathFor(role: UserRole): string {
  return role === "admin" ? "/admin" : role === "publisher" ? "/publisher" : "/user";
}
