import { GoogleAuthProvider, onAuthStateChanged, signInWithPopup, signOut as fbSignOut, type User } from "firebase/auth";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { auth } from "../lib/firebase";

interface AuthState {
  user: User | null;
  loading: boolean;
  signIn(): Promise<void>;
  signOut(): Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(Boolean(auth));

  useEffect(() => {
    if (!auth) return;
    return onAuthStateChanged(auth, (u) => {
      setUser(u);
      setLoading(false);
    });
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      async signIn() {
        if (!auth) throw new Error("Firebase isn't configured. Fill in frontend/.env.");
        try {
          await signInWithPopup(auth, new GoogleAuthProvider());
        } catch (e) {
          const code = (e as { code?: string }).code;
          if (code === "auth/popup-closed-by-user" || code === "auth/cancelled-popup-request") return;
          throw e;
        }
      },
      async signOut() {
        if (auth) await fbSignOut(auth);
      },
    }),
    [user, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
