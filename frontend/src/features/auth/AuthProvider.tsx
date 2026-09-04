import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { ApiError, apiRequest, apiVoid, onAuthenticationFailure, setCsrfToken } from "../../shared/api/http";
import { SessionSchema, type Session } from "../../shared/fhir/schemas";
import { ErrorState, FullPageState } from "../../shared/components/States";

type AuthContextValue = Session & { logout: () => Promise<void> };
const AuthContext = createContext<AuthContextValue | null>(null);

function safeReturnPath(): string {
  return ["/", "/patients", "/patient"].includes(window.location.pathname)
    ? window.location.pathname
    : "/";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [accessDenied, setAccessDenied] = useState(false);
  const sessionQuery = useQuery({
    queryKey: ["session"],
    queryFn: () => apiRequest("/auth/session", SessionSchema),
    retry: false,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (sessionQuery.data) setCsrfToken(sessionQuery.data.csrfToken);
    return () => setCsrfToken(null);
  }, [sessionQuery.data]);

  useEffect(() => {
    const handleSecurityFailure = (kind: "unauthorized" | "forbidden") => {
      setCsrfToken(null);
      queryClient.clear();
      if (kind === "forbidden") setAccessDenied(true);
      else window.location.replace(`/auth/login?return_to=${encodeURIComponent(safeReturnPath())}`);
    };
    onAuthenticationFailure(handleSecurityFailure);
    if (sessionQuery.error instanceof ApiError && sessionQuery.error.kind === "unauthorized") {
      handleSecurityFailure("unauthorized");
    }
    return () => onAuthenticationFailure(null);
  }, [queryClient, sessionQuery.error]);

  if (accessDenied) {
    return <FullPageState title="Kein Zugriff" message="Für diese Ansicht fehlt die erforderliche Berechtigung. Es werden keine Patientendaten angezeigt." />;
  }

  if (sessionQuery.isError) {
    return <main className="centered-page"><div className="state-card"><ErrorState error={sessionQuery.error} onRetry={() => void sessionQuery.refetch()} /></div></main>;
  }

  if (!sessionQuery.data) {
    return <FullPageState title="Sichere Sitzung wird geprüft" message="Sie werden bei Bedarf zur Anmeldung weitergeleitet." loading />;
  }

  setCsrfToken(sessionQuery.data.csrfToken);

  const logout = async () => {
    await apiVoid("/auth/logout", { method: "POST" });
    setCsrfToken(null);
    queryClient.clear();
    window.location.replace("/");
  };

  return <AuthContext.Provider value={{ ...sessionQuery.data, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider fehlt.");
  return value;
}
